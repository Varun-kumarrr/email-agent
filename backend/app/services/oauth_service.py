"""OAuth connection flow for email accounts (Gmail now; the design is provider-neutral).

Security:
- `state` is 32 random bytes (secrets.token_urlsafe). Only its SHA-256 hash is stored,
  together with the user/company that started the flow; no IDs travel in the state.
- PKCE (S256): the code verifier is Fernet-encrypted at rest and sent only to Google.
- A state expires after OAUTH_STATE_TTL_SECONDS and is consumed exactly once (row
  lock + consumed_at), *before* the code is exchanged, so a replay always fails.
- The callback never reveals tokens or codes; it redirects to a fixed frontend URL
  with only a safe status/reason (no open redirect).
"""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.models import AccountType, Company, EmailAccount, EmailProvider, OAuthState, User
from app.services import google_oauth
from app.services.email_account_service import EmailAccountService
from app.services.google_oauth import GoogleOAuthError

logger = logging.getLogger(__name__)


class OAuthFlowError(Exception):
    """Safe, user-facing failure of the connect flow; `reason` goes into the redirect URL."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class ConnectResult:
    account: EmailAccount
    created: bool


def _hash_state(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def create_state(db: Session, user: User, company: Company, provider: EmailProvider) -> tuple[str, str]:
    """Create a one-time state. Returns (state, pkce_code_challenge)."""
    now = datetime.now(timezone.utc)
    # Housekeeping: drop states that expired more than a day ago.
    db.execute(delete(OAuthState).where(OAuthState.expires_at < now - timedelta(days=1)))

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)  # 86 chars, within PKCE's 43-128
    db.add(
        OAuthState(
            state_hash=_hash_state(state),
            provider=provider,
            user_id=user.id,
            company_id=company.id,
            encrypted_code_verifier=encrypt_secret(verifier),
            expires_at=now + timedelta(seconds=settings.OAUTH_STATE_TTL_SECONDS),
        )
    )
    db.commit()
    return state, _pkce_challenge(verifier)


def consume_state(db: Session, state: str | None, provider: EmailProvider) -> tuple[OAuthState, str]:
    """Validate and consume a state exactly once. Returns (state_row, pkce_code_verifier)."""
    if not state or len(state) > 200:
        raise OAuthFlowError("state_missing" if not state else "state_invalid")
    row = db.scalar(select(OAuthState).where(OAuthState.state_hash == _hash_state(state)).with_for_update())
    if row is None or row.provider != provider:
        db.rollback()
        raise OAuthFlowError("state_invalid")
    if row.consumed_at is not None:
        db.rollback()
        raise OAuthFlowError("state_used")
    now = datetime.now(timezone.utc)
    row.consumed_at = now  # consumed even if what follows fails: a state is never usable twice
    db.commit()
    if row.expires_at <= now:
        raise OAuthFlowError("state_expired")
    return row, decrypt_secret(row.encrypted_code_verifier)


def complete_gmail_connection(db: Session, *, state: str | None, code: str | None, error: str | None) -> ConnectResult:
    row, verifier = consume_state(db, state, EmailProvider.GMAIL)

    if error:
        # e.g. access_denied when the user clicks "Cancel" on Google's consent screen.
        raise OAuthFlowError("access_denied" if error == "access_denied" else "provider_error")
    if not code:
        raise OAuthFlowError("code_missing")

    company = db.get(Company, row.company_id)
    user = db.get(User, row.user_id)
    if company is None or user is None or company.user_id != user.id or not user.is_active:
        raise OAuthFlowError("account_mismatch")

    try:
        tokens = google_oauth.exchange_code(code, verifier)
        if google_oauth.GMAIL_SEND_SCOPE not in tokens.scopes:
            raise OAuthFlowError("scope_missing")  # the user unticked "Send email on your behalf"
        email = google_oauth.fetch_verified_email(tokens.access_token)
    except GoogleOAuthError as err:
        logger.warning("Gmail OAuth connection failed code=%s", err.code)
        raise OAuthFlowError(err.code)

    return _upsert_gmail_account(db, company, user, email, tokens)


def _upsert_gmail_account(db: Session, company: Company, user: User, email: str, tokens) -> ConnectResult:
    existing = db.scalar(
        select(EmailAccount).where(
            EmailAccount.company_id == company.id,
            EmailAccount.account_type == AccountType.OAUTH,
            EmailAccount.email_address == email,
        )
    )
    encrypted_access = encrypt_secret(tokens.access_token)
    encrypted_refresh = encrypt_secret(tokens.refresh_token) if tokens.refresh_token else None
    scopes = " ".join(tokens.scopes)[:500]

    if existing is not None:  # reconnect: refresh the credentials, keep the account's settings
        existing.encrypted_oauth_access_token = encrypted_access
        if encrypted_refresh:  # Google may omit it; keep the previous refresh token then
            existing.encrypted_oauth_refresh_token = encrypted_refresh
        existing.oauth_token_expires_at = tokens.expires_at
        existing.oauth_scopes = scopes
        existing.last_tested_at = None
        existing.last_test_success = None
        db.commit()
        return ConnectResult(existing, created=False)

    if not encrypted_refresh:
        raise OAuthFlowError("refresh_token_missing")
    account = EmailAccount(
        company_id=company.id,
        account_name=f"Gmail ({email})"[:120],
        provider=EmailProvider.GMAIL,
        account_type=AccountType.OAUTH,
        email_address=email,
        sender_name=(user.name or company.name)[:120],
        encrypted_oauth_access_token=encrypted_access,
        encrypted_oauth_refresh_token=encrypted_refresh,
        oauth_token_expires_at=tokens.expires_at,
        oauth_scopes=scopes,
        is_active=True,
        is_default=False,
    )
    return ConnectResult(EmailAccountService(db).save_oauth_account(company, account), created=True)
