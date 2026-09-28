import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EmailFormat, EmailStatus, SecurityType

if TYPE_CHECKING:
    from app.models.company import Company


def _enum(enum_cls):
    # Stored as VARCHAR + CHECK constraint: portable and easy to extend in migrations.
    return Enum(enum_cls, native_enum=False, length=20, validate_strings=True)


class EmailConfiguration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The company's own SMTP account. Every email the company sends goes through it."""

    __tablename__ = "email_configurations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    # Fernet-encrypted ciphertext. The plaintext password is never stored or returned.
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    security_type: Mapped[SecurityType] = mapped_column(_enum(SecurityType), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reply_to: Mapped[str | None] = mapped_column(String(255))

    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_success: Mapped[bool | None] = mapped_column(Boolean)

    company: Mapped["Company"] = relationship(back_populates="email_configuration")


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
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(120))
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    cc: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    bcc: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    email_format: Mapped[EmailFormat] = mapped_column(_enum(EmailFormat), nullable=False)
    status: Mapped[EmailStatus] = mapped_column(_enum(EmailStatus), nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(String(500))
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship(back_populates="email_history")
