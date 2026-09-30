"""Email account schemas.

Credentials (SMTP password, OAuth tokens) are write-only or never accepted at all:
responses expose only `password_configured` / `oauth_connected` flags.
OAuth accounts are created through the OAuth connect flow, not through this API.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import AccountType, EmailProvider, SecurityType
from app.schemas.common import SingleLineText, Text
from app.schemas.email_config import SmtpHost, SmtpPassword, SmtpPort

# Well-known SMTP settings used when the provider is chosen and host/port are omitted.
SMTP_PRESETS: dict[EmailProvider, dict] = {
    EmailProvider.GMAIL: {"smtp_host": "smtp.gmail.com", "smtp_port": 587, "security_type": SecurityType.STARTTLS},
    EmailProvider.OUTLOOK: {"smtp_host": "smtp.office365.com", "smtp_port": 587, "security_type": SecurityType.STARTTLS},
}


class EmailAccountCreate(BaseModel):
    """Create an SMTP email account (Gmail, Outlook or any public/generic SMTP server)."""

    account_name: Text(120, min_length=1) = Field(examples=["Sales mailbox"])
    provider: EmailProvider = Field(default=EmailProvider.GENERIC, examples=[EmailProvider.GMAIL])
    email_address: EmailStr = Field(examples=["anjali@abctech.com"])
    sender_name: SingleLineText(120, min_length=1) = Field(examples=["Anjali from ABC Technologies"])
    reply_to: EmailStr | None = None
    smtp_host: SmtpHost | None = Field(default=None, description="Optional for GMAIL/OUTLOOK (preset used).")
    smtp_port: SmtpPort | None = None
    smtp_username: Text(255, min_length=1) | None = Field(default=None, description="Defaults to email_address.")
    password: SmtpPassword = Field(description="SMTP password or app password. Write-only; stored encrypted.")
    security_type: SecurityType | None = None
    is_active: bool = True
    is_default: bool = Field(default=False, description="The first account of a company always becomes default.")

    @model_validator(mode="after")
    def apply_preset(self):
        preset = SMTP_PRESETS.get(self.provider, {})
        for field, value in preset.items():
            if getattr(self, field) is None:
                setattr(self, field, value)
        missing = [f for f in ("smtp_host", "smtp_port", "security_type") if getattr(self, f) is None]
        if missing:
            raise ValueError(f"{', '.join(missing)} required for provider {self.provider.value}")
        if self.smtp_username is None:
            self.smtp_username = str(self.email_address)
        return self


class EmailAccountUpdate(BaseModel):
    """Partial update (PATCH). Omitted fields are unchanged; omit `password` to keep it."""

    account_name: Text(120, min_length=1) | None = None
    email_address: EmailStr | None = None
    sender_name: SingleLineText(120, min_length=1) | None = None
    reply_to: EmailStr | None = Field(default=None, description="Send null to clear.")
    smtp_host: SmtpHost | None = None
    smtp_port: SmtpPort | None = None
    smtp_username: Text(255, min_length=1) | None = None
    password: SmtpPassword | None = Field(default=None, description="Write-only. Omit to keep the stored password.")
    security_type: SecurityType | None = None
    is_active: bool | None = None


class EmailAccountResponse(BaseModel):
    """Never contains passwords or tokens."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_name: str
    provider: EmailProvider
    account_type: AccountType
    email_address: str
    sender_name: str
    reply_to: str | None
    smtp_host: str | None
    smtp_port: int | None
    smtp_username: str | None
    security_type: SecurityType | None
    password_configured: bool
    oauth_connected: bool
    oauth_token_expires_at: datetime | None
    is_active: bool
    is_default: bool
    last_tested_at: datetime | None
    last_test_success: bool | None
    created_at: datetime
    updated_at: datetime


class EmailAccountTestRequest(BaseModel):
    recipient: EmailStr = Field(description="Where to send the test email.")
