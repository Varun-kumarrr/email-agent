import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.email import _enum
from app.models.enums import EmailProvider


class OAuthState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One pending OAuth authorization (CSRF protection + PKCE).

    The browser only ever carries a random `state`; this row links it to the user and
    company that started the flow. Only a SHA-256 hash of the state is stored, the PKCE
    verifier is Fernet-encrypted, and the row can be consumed exactly once before it expires.
    """

    __tablename__ = "oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    provider: Mapped[EmailProvider] = mapped_column(_enum(EmailProvider), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    encrypted_code_verifier: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
