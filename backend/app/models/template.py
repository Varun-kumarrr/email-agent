import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.email import _enum
from app.models.enums import EmailFormat

if TYPE_CHECKING:
    from app.models.company import Company


class EmailTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reusable, company-owned email template with `{{ variable }}` placeholders."""

    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_email_templates_company_name"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(60))
    subject_template: Mapped[str] = mapped_column(String(300), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[EmailFormat] = mapped_column(_enum(EmailFormat), nullable=False)
    # Placeholder names found in subject/body, kept in sync on every save.
    variables: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="email_templates")
