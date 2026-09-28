"""Sends email through one of the authenticated company's own email accounts.

Flow: user -> company -> selected email account (or the company default) ->
preferences -> sender / reply-to -> signature -> history record (QUEUED) ->
delivery -> history updated -> safe result.

Delivery happens either inline (EMAIL_DELIVERY_MODE=sync, retries inline) or in
the background by the Celery worker (EMAIL_DELIVERY_MODE=celery), in which case
the API returns immediately with the QUEUED history record.

There is no system-wide sender: the From address is always the selected account's
address, and credentials come only from that account.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, EmailDeliveryError, RateLimitError, ServiceUnavailableError
from app.models import Company, EmailHistory, EmailStatus, User
from app.schemas.email import SendEmailRequest, SendEmailResponse
from app.services.email_account_service import EmailAccountService
from app.services.email_delivery import AttemptResult, deliver_now, finalize_body
from app.services.preferences_service import PreferencesService
from app.services.signature_service import SignatureService
from app.utils.signature import ends_with_signature

logger = logging.getLogger(__name__)


def enqueue_delivery(history_id: uuid.UUID) -> str:
    """Hand the email to the Celery worker. Returns the task id."""
    from app.worker.tasks import send_email_task  # imported lazily: sync mode never needs Celery

    return send_email_task.apply_async(args=[str(history_id)]).id


class EmailSenderService:
    def __init__(self, db: Session):
        self.db = db

    def send(self, company: Company, user: User, data: SendEmailRequest) -> SendEmailResponse:
        account = EmailAccountService(self.db).resolve_for_sending(company, data.email_account_id)

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

        sender_name = prefs.sender_name or account.sender_name
        reply_to = prefs.reply_to or account.reply_to

        signature = SignatureService(self.db).active_signature(company)
        wants_signature = (
            data.append_signature if data.append_signature is not None
            else bool(signature and signature.append_automatically)
        )
        signature_text = None
        if wants_signature and signature is not None and not ends_with_signature(data.body, signature.signature_text):
            signature_text = signature.signature_text

        # Record the email first (QUEUED): this row is what the worker delivers and updates.
        record = EmailHistory(
            company_id=company.id,
            sent_by_user_id=user.id,
            email_account_id=account.id,
            sender_email=account.email_address,
            sender_name=sender_name,
            reply_to=reply_to,
            recipient=recipient,
            cc=cc,
            bcc=bcc,
            subject=data.subject,
            body=finalize_body(data.body, signature_text, email_format),
            email_format=email_format,
            status=EmailStatus.QUEUED,
            attempts=0,
        )
        self.db.add(record)
        self.db.commit()

        if settings.EMAIL_DELIVERY_MODE == "celery":
            try:
                record.task_id = enqueue_delivery(record.id)
                self.db.commit()
            except Exception as exc:  # broker unreachable
                logger.error("Could not queue email %s: %s", record.id, type(exc).__name__)
                record.status = EmailStatus.FAILED
                record.error_code = "queue_unavailable"
                record.error_message = "The background email queue is unavailable. Please try again later."
                self.db.commit()
                raise ServiceUnavailableError(
                    record.error_message, details={"history_id": str(record.id), "error_code": record.error_code}
                )
            return self._response(record, account.id, signature_text, f"Email to {recipient} queued for delivery.")

        outcome = deliver_now(self.db, record.id)
        self.db.refresh(record)
        if outcome.result != AttemptResult.SENT:
            error = outcome.error
            raise EmailDeliveryError(
                record.error_message or "The email could not be sent",
                details={
                    "history_id": str(record.id),
                    "error_code": error.code if error else record.error_code,
                    "attempts": record.attempts,
                },
            )
        return self._response(record, account.id, signature_text, f"Email sent to {recipient}.")

    @staticmethod
    def _response(record: EmailHistory, account_id, signature_text, message: str) -> SendEmailResponse:
        return SendEmailResponse(
            id=record.id,
            status=record.status,
            message=message,
            email_account_id=account_id,
            sender_email=record.sender_email,
            sender_name=record.sender_name,
            recipient=record.recipient,
            cc=list(record.cc),
            bcc=list(record.bcc),
            subject=record.subject,
            format=record.email_format,
            signature_appended=signature_text is not None,
            attempts=record.attempts,
            sent_at=record.sent_at,
            task_id=record.task_id,
        )
