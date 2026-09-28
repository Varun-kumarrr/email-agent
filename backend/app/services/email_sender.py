"""Sends email through the authenticated company's own SMTP account.

Flow: user -> company -> company's SMTP configuration -> preferences ->
sender / reply-to -> signature -> send (with retries on transient errors) ->
history record -> safe result.

There is no system-wide sender: the From address is always the company's
configured SMTP email, and credentials come only from that configuration.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, EmailDeliveryError, NotFoundError, RateLimitError
from app.models import Company, EmailHistory, EmailStatus, User
from app.schemas.email import SendEmailRequest, SendEmailResponse
from app.services import smtp_client
from app.services.email_composer import build_message
from app.services.email_config_service import EmailConfigService, build_credentials
from app.services.preferences_service import PreferencesService
from app.services.signature_service import SignatureService
from app.services.smtp_client import SmtpSendError
from app.utils.signature import ends_with_signature

logger = logging.getLogger(__name__)


class EmailSenderService:
    def __init__(self, db: Session):
        self.db = db

    def send(self, company: Company, user: User, data: SendEmailRequest) -> SendEmailResponse:
        config = EmailConfigService(self.db).find(company)
        if config is None:
            raise NotFoundError("Configure your SMTP email account before sending emails.")

        prefs_service = PreferencesService(self.db)
        prefs = prefs_service.get(company)

        email_format = data.format or prefs.default_format
        cc = data.cc if data.cc is not None else list(prefs.default_cc or [])
        bcc = data.bcc if data.bcc is not None else list(prefs.default_bcc or [])
        recipient = data.recipient.lower()
        cc = [a for a in cc if a != recipient]
        bcc = [a for a in bcc if a != recipient and a not in cc]
        envelope = [recipient, *cc, *bcc]

        if len(envelope) > prefs.max_recipients_per_email:
            raise BadRequestError(
                f"Too many recipients ({len(envelope)}). Your limit is {prefs.max_recipients_per_email} per email."
            )
        if prefs_service.sent_today(company) >= prefs.daily_send_limit:
            raise RateLimitError(f"Daily sending limit of {prefs.daily_send_limit} emails reached.")

        sender_name = prefs.sender_name or config.sender_name
        reply_to = prefs.reply_to or config.reply_to

        signature = SignatureService(self.db).active_signature(company)
        wants_signature = (
            data.append_signature if data.append_signature is not None
            else bool(signature and signature.append_automatically)
        )
        signature_text = None
        if wants_signature and signature is not None and not ends_with_signature(data.body, signature.signature_text):
            signature_text = signature.signature_text

        message = build_message(
            sender_email=config.email,
            sender_name=sender_name,
            recipient=recipient,
            subject=data.subject,
            body=data.body,
            email_format=email_format,
            cc=cc,
            reply_to=reply_to,
            signature=signature_text,
        )
        final_body = data.body if not signature_text else f"{data.body.rstrip()}\n\n{signature_text.strip()}"

        attempts, error = self._deliver(config, message, envelope, max_retries=prefs.max_send_retries)

        now = datetime.now(timezone.utc)
        record = EmailHistory(
            company_id=company.id,
            sent_by_user_id=user.id,
            sender_email=config.email,
            sender_name=sender_name,
            recipient=recipient,
            cc=cc,
            bcc=bcc,
            subject=data.subject,
            body=final_body,
            email_format=email_format,
            status=EmailStatus.FAILED if error else EmailStatus.SENT,
            error_message=error.message if error else None,  # safe, pre-classified message only
            attempts=attempts,
            sent_at=None if error else now,
        )
        self.db.add(record)
        self.db.commit()

        if error:
            raise EmailDeliveryError(
                error.message,
                details={"history_id": str(record.id), "error_code": error.code, "attempts": attempts},
            )
        return SendEmailResponse(
            id=record.id,
            status=record.status,
            message=f"Email sent to {recipient}.",
            sender_email=config.email,
            sender_name=sender_name,
            recipient=recipient,
            cc=cc,
            bcc=bcc,
            subject=data.subject,
            format=email_format,
            signature_appended=signature_text is not None,
            attempts=attempts,
            sent_at=now,
        )

    def _deliver(self, config, message, envelope, *, max_retries: int) -> tuple[int, SmtpSendError | None]:
        """Send with retries on transient failures only. Returns (attempts, error or None)."""
        attempts = 0
        while True:
            attempts += 1
            try:
                smtp_client.send_message(build_credentials(config), message, envelope)
                return attempts, None
            except SmtpSendError as error:
                if not error.transient or attempts > max_retries:
                    return attempts, error
                logger.info("Transient SMTP error code=%s; retrying (attempt %s)", error.code, attempts + 1)
                time.sleep(settings.SMTP_RETRY_BACKOFF_SECONDS * attempts)
