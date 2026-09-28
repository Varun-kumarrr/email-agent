import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.email import EmailAccount, EmailHistory, EmailPreferences, EmailSignature
    from app.models.user import User


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    # unique=True enforces the one-user-one-company rule at the database level.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(200))

    # Contact information
    contact_person: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(String(500))

    owner: Mapped["User"] = relationship(back_populates="company")

    services: Mapped[list["CompanyService"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="CompanyService.position"
    )
    target_customers: Mapped[list["TargetCustomer"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="TargetCustomer.position"
    )
    value_propositions: Mapped[list["ValueProposition"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="ValueProposition.position"
    )
    social_links: Mapped[list["SocialLink"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="SocialLink.position"
    )

    email_accounts: Mapped[list["EmailAccount"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="EmailAccount.created_at"
    )
    signature: Mapped["EmailSignature | None"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    preferences: Mapped["EmailPreferences | None"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    email_history: Mapped[list["EmailHistory"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class CompanyService(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A product or service offered by the company."""

    __tablename__ = "company_services"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(default=0, nullable=False)

    company: Mapped[Company] = relationship(back_populates="services")


class TargetCustomer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "target_customers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    segment: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(default=0, nullable=False)

    company: Mapped[Company] = relationship(back_populates="target_customers")


class ValueProposition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "value_propositions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(default=0, nullable=False)

    company: Mapped[Company] = relationship(back_populates="value_propositions")


class SocialLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "social_links"
    __table_args__ = (UniqueConstraint("company_id", "url", name="uq_social_links_company_url"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(60), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[int] = mapped_column(default=0, nullable=False)

    company: Mapped[Company] = relationship(back_populates="social_links")
