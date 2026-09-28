"""Email delivery: one attempt at a time, driven either inline (sync mode) or by the
Celery worker (background mode).

State machine for an EmailHistory row:

    QUEUED --> SENDING --> SENT
                  |
                  +--> RETRYING --> SENDING --> ...   (transient errors, bounded)
                  |
                  +--> FAILED                         (permanent error or retries exhausted)

Duplicate prevention: an attempt locks the row (SELECT ... FOR UPDATE) and only
proceeds when the status is QUEUED or RETRYING, then marks it SENDING before
contacting the provider. A re-delivered or duplicate task for a row that is
already SENDING/SENT/FAILED does nothing, so an email is never sent twice.
"""

import html
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AccountType, EmailAccount, EmailFormat, EmailHistory, EmailStatus
from app.services import smtp_client
from app.services.email_account_service import build_smtp_credentials, with_provider_hint
from app.services.email_composer import build_message, looks_like_html
from app.services.gmail_delivery import is_gmail_oauth, send_via_gmail
from app.services.preferences_service import PreferencesService
from app.services.smtp_client import SmtpSendError
from app.utils.signature import append_signature

logger = logging.getLogger(__name__)


class AttemptResult(str, Enum):
    SENT = "sent"
    RETRY = "retry"  # transient failure; schedule another attempt
    FAILED = "failed"  # permanent failure or retries exhausted
    SKIPPED = "skipped"  # already handled (duplicate/redelivered task) or missing


@dataclass
class DeliveryOutcome:
    result: AttemptResult
    attempts: int = 0
    error: SmtpSendError | None = None


def finalize_body(body: str, signature: str | None, email_format: EmailFormat) -> str:
    """The exact body that will be sent and stored in history (signature appended once)."""
    if not signature:
        return body
    if email_format == EmailFormat.HTML and looks_like_html(body):
        return f"{body}<br><br>{html.escape(signature.strip()).replace(chr(10), '<br>')}"
    return append_signature(body, signature)


def retry_delay_seconds(attempts: int) -> float:
    """Exponential backoff with jitter, capped: base * 2^(attempts-1) (+/- 10%)."""
    delay = min(settings.EMAIL_RETRY_BASE_SECONDS * (2 ** max(attempts - 1, 0)), settings.EMAIL_RETRY_MAX_SECONDS)
    return round(delay * random.uniform(0.9, 1.1), 1)


def _send_through_account(db: Session, account: EmailAccount, record: EmailHistory) -> None:
    """Build the MIME message from the history row and send it through the account."""
    message = build_message(
        sender_email=account.email_address,
        sender_name=record.sender_name,
        recipient=record.recipient,
        subject=record.subject,
        body=record.body,
        email_format=record.email_format,
        cc=list(record.cc or []),
        reply_to=record.reply_to,
        signature=None,  # already part of record.body
    )
    envelope = [record.recipient, *(record.cc or []), *(record.bcc or [])]
    if account.account_type == AccountType.SMTP:
        smtp_client.send_message(build_smtp_credentials(account), message, envelope)
        return
    if is_gmail_oauth(account):
        send_via_gmail(db, account, message, list(record.bcc or []))
        return
    raise SmtpSendError("not_supported", "Sending through this account type is not supported yet.")


def attempt_delivery(db: Session, history_id: uuid.UUID) -> DeliveryOutcome:
    """Make one delivery attempt for a history row and record the result."""
    # 1. Claim the row: lock it and only continue if it is waiting to be sent.
    record = db.scalar(select(EmailHistory).where(EmailHistory.id == history_id).with_for_update())
    if record is None or record.status not in (EmailStatus.QUEUED, EmailStatus.RETRYING):
        db.rollback()
        return DeliveryOutcome(AttemptResult.SKIPPED, attempts=record.attempts if record else 0)

    record.status = EmailStatus.SENDING
    record.attempts += 1
    record.last_attempt_at = datetime.now(timezone.utc)
    db.commit()  # releases the lock; other workers now see SENDING and skip

    # 2. Send through the company's own account.
    account = db.get(EmailAccount, record.email_account_id) if record.email_account_id else None
    try:
        if account is None or account.company_id != record.company_id:
            raise SmtpSendError("account_unavailable", "The email account used for this email no longer exists.")
        if not account.is_active:
            raise SmtpSendError("account_inactive", "The email account used for this email is inactive.")
        _send_through_account(db, account, record)
    except SmtpSendError as error:
        if account is not None:
            error = with_provider_hint(error, account.provider)
        max_retries = PreferencesService(db).get_for_company_id(record.company_id).max_send_retries
        retry = error.transient and record.attempts <= max_retries
        record.status = EmailStatus.RETRYING if retry else EmailStatus.FAILED
        record.error_code = error.code
        record.error_message = error.message  # safe, pre-classified message only
        db.commit()
        logger.info(
            "Email %s attempt %s failed code=%s -> %s", record.id, record.attempts, error.code, record.status.value
        )
        return DeliveryOutcome(AttemptResult.RETRY if retry else AttemptResult.FAILED, record.attempts, error)

    record.status = EmailStatus.SENT
    record.sent_at = datetime.now(timezone.utc)
    record.error_code = None
    record.error_message = None
    db.commit()
    return DeliveryOutcome(AttemptResult.SENT, record.attempts)


def deliver_now(db: Session, history_id: uuid.UUID, *, sleep=None) -> DeliveryOutcome:
    """Synchronous mode: attempt, and retry transient failures inline with a short backoff."""
    import time

    sleep = sleep or time.sleep
    while True:
        outcome = attempt_delivery(db, history_id)
        if outcome.result != AttemptResult.RETRY:
            return outcome
        sleep(settings.SMTP_RETRY_BACKOFF_SECONDS * outcome.attempts)
