from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company, EmailFormat, EmailHistory, EmailPreferences, EmailStatus
from app.schemas.preferences import PreferencesResponse, PreferencesUpdate, SignatureSummary
from app.services.email_account_service import EmailAccountService
from app.services.signature_service import SignatureService

DEFAULTS = PreferencesUpdate()


def _default_preferences(company: Company) -> EmailPreferences:
    """Unsaved preferences filled with defaults, used until the company saves its own."""
    return EmailPreferences(company_id=company.id, **DEFAULTS.model_dump())


class PreferencesService:
    def __init__(self, db: Session):
        self.db = db

    def _find(self, company: Company) -> EmailPreferences | None:
        return self.db.scalar(select(EmailPreferences).where(EmailPreferences.company_id == company.id))

    def get(self, company: Company) -> EmailPreferences:
        return self._find(company) or _default_preferences(company)

    def update(self, company: Company, data: PreferencesUpdate) -> EmailPreferences:
        prefs = self._find(company)
        if prefs is None:
            prefs = EmailPreferences(company_id=company.id)
            self.db.add(prefs)
        for field, value in data.model_dump().items():
            setattr(prefs, field, value)
        self.db.commit()
        return prefs

    def sent_today(self, company: Company) -> int:
        start_of_day = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
        count = self.db.scalar(
            select(func.count(EmailHistory.id)).where(
                EmailHistory.company_id == company.id,
                EmailHistory.status == EmailStatus.SENT,
                EmailHistory.created_at >= start_of_day,
            )
        )
        return count or 0

    def to_response(self, company: Company, prefs: EmailPreferences) -> PreferencesResponse:
        account = EmailAccountService(self.db).default_account(company)  # default sender account
        signature = SignatureService(self.db).find(company)
        sent_today = self.sent_today(company)
        return PreferencesResponse(
            sender_name=prefs.sender_name,
            reply_to=prefs.reply_to,
            default_format=prefs.default_format or EmailFormat.PLAIN_TEXT,
            daily_send_limit=prefs.daily_send_limit,
            max_recipients_per_email=prefs.max_recipients_per_email,
            max_send_retries=prefs.max_send_retries,
            default_cc=prefs.default_cc or [],
            default_bcc=prefs.default_bcc or [],
            extra_settings=prefs.extra_settings or {},
            effective_sender_name=prefs.sender_name or (account.sender_name if account else None),
            effective_reply_to=prefs.reply_to or (account.reply_to if account else None),
            signature=SignatureSummary(
                configured=signature is not None,
                enabled=bool(signature and signature.enabled),
                append_automatically=bool(signature and signature.append_automatically),
            ),
            sent_today=sent_today,
            remaining_today=max(prefs.daily_send_limit - sent_today, 0),
            updated_at=prefs.updated_at,
        )
