import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AccountType, EmailFormat, EmailProvider, EmailStatus, SecurityType

if TYPE_CHECKING:
    from app.models.company import Company


def _enum(enum_cls):
    # Stored as VARCHAR (no database CHECK constraint): values are validated by SQLAlchemy
    # (validate_strings) and by the Pydantic schemas, and new values need no migration.
    return Enum(enum_cls, native_enum=False, length=20, validate_strings=True)


class EmailAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One mailbox the company can send from. A company can have many; exactly one may be default.

    SMTP accounts store host/port/username and a Fernet-encrypted password.
    OAuth accounts (Gmail / Outlook) store Fernet-encrypted access and refresh tokens.
    No credential is ever stored in plaintext or returned by the API.
    """

    __tablename__ = "email_accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "account_type", "email_address", name="uq_email_accounts_company_type_email"),
        # At most one default account per company (partial unique index, PostgreSQL).
        Index(
            "uq_email_accounts_one_default_per_company",
            "company_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[EmailProvider] = mapped_column(_enum(EmailProvider), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(_enum(AccountType), nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reply_to: Mapped[str | None] = mapped_column(String(255))

    # SMTP accounts
    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int | None] = mapped_column(Integer)
    smtp_username: Mapped[str | None] = mapped_column(String(255))
    encrypted_smtp_password: Mapped[str | None] = mapped_column(Text)  # Fernet ciphertext
    security_type: Mapped[SecurityType | None] = mapped_column(_enum(SecurityType))

    # OAuth accounts (the OAuth provider is `provider`: GMAIL or OUTLOOK)
    encrypted_oauth_access_token: Mapped[str | None] = mapped_column(Text)  # Fernet ciphertext
    encrypted_oauth_refresh_token: Mapped[str | None] = mapped_column(Text)  # Fernet ciphertext
    oauth_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    oauth_scopes: Mapped[str | None] = mapped_column(String(500))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_success: Mapped[bool | None] = mapped_column(Boolean)

    company: Mapped["Company"] = relationship(back_populates="email_accounts")

    def __repr__(self) -> str:  # never include credentials
        return f"EmailAccount(id={self.id}, type={self.account_type}, provider={self.provider}, email={self.email_address!r})"


class EmailSignature(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_signatures"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    signature_text: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    append_automatically: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="signature")


class EmailPreferences(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Sending preferences. Explicit columns for known preferences plus a JSON column
    (`extra_settings`) so new, less critical preferences can be added without a migration."""

    __tablename__ = "email_preferences"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Overrides for the values on the email configuration (null = use configuration value).
    sender_name: Mapped[str | None] = mapped_column(String(120))
    reply_to: Mapped[str | None] = mapped_column(String(255))

    default_format: Mapped[EmailFormat] = mapped_column(
        _enum(EmailFormat), default=EmailFormat.PLAIN_TEXT, nullable=False
    )
    daily_send_limit: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_recipients_per_email: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_send_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    default_cc: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    default_bcc: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    extra_settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="preferences")


class EmailHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audit log of every send attempt. Never contains credentials or tokens."""

    __tablename__ = "email_history"
    __table_args__ = (Index("ix_email_history_company_created", "company_id", "created_at"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    # The account used for sending. SET NULL keeps history when an account is deleted
    # (sender_email/sender_name below still record who sent it).
    email_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("email_accounts.id", ondelete="SET NULL"), index=True
    )
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(120))
    reply_to: Mapped[str | None] = mapped_column(String(255))
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    cc: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    bcc: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    email_format: Mapped[EmailFormat] = mapped_column(_enum(EmailFormat), nullable=False)
    status: Mapped[EmailStatus] = mapped_column(_enum(EmailStatus), nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(String(500))  # safe, pre-classified text only
    error_code: Mapped[str | None] = mapped_column(String(60))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(64))  # Celery task id (background mode)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship(back_populates="email_history")
