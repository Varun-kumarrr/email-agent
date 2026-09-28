from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

from app.models.enums import EmailFormat
from app.schemas.common import Text


def _dedupe(emails: list[str]) -> list[str]:
    seen: list[str] = []
    for email in emails:
        email = email.lower()
        if email not in seen:
            seen.append(email)
    return seen


EmailList = Annotated[list[EmailStr], Field(max_length=20), AfterValidator(_dedupe)]
ExtraValue = str | int | float | bool | None


class PreferencesUpdate(BaseModel):
    sender_name: Text(120) | None = Field(
        default=None, description="Overrides the sender name from the email configuration."
    )
    reply_to: EmailStr | None = Field(
        default=None, description="Overrides the reply-to address from the email configuration."
    )
    default_format: EmailFormat = EmailFormat.PLAIN_TEXT
    daily_send_limit: int = Field(default=100, ge=1, le=10000, description="Max emails sent per UTC day.")
    max_recipients_per_email: int = Field(default=10, ge=1, le=50, description="To + CC + BCC.")
    max_send_retries: int = Field(default=2, ge=0, le=5, description="Retries on transient SMTP errors.")
    default_cc: EmailList = Field(default_factory=list)
    default_bcc: EmailList = Field(default_factory=list)
    extra_settings: dict[str, ExtraValue] = Field(
        default_factory=dict, description="Room for future preferences without schema changes."
    )

    @field_validator("sender_name")
    @classmethod
    def empty_to_none(cls, value):
        return value or None

    @field_validator("extra_settings")
    @classmethod
    def limit_extra(cls, value: dict):
        if len(value) > 30 or any(len(k) > 60 for k in value):
            raise ValueError("Too many or too long extra settings")
        return value


class SignatureSummary(BaseModel):
    configured: bool
    enabled: bool
    append_automatically: bool


class PreferencesResponse(PreferencesUpdate):
    effective_sender_name: str | None = Field(description="Sender name that will actually be used.")
    effective_reply_to: str | None = Field(description="Reply-to that will actually be used.")
    signature: SignatureSummary = Field(description="The default signature (managed via /signature).")
    sent_today: int
    remaining_today: int
    updated_at: datetime | None = None
