"""Delivery through a Gmail OAuth account (Gmail API, not SMTP).

Access tokens are refreshed automatically from the Fernet-encrypted refresh token,
and the refreshed access token is encrypted before it is stored. Token values are
never logged or returned. Failures are converted into the same safe delivery errors
the SMTP path uses, so history, retries and the Celery worker behave identically.
"""

import copy
import logging
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import DecryptionError, decrypt_secret, encrypt_secret
from app.models import AccountType, EmailAccount, EmailProvider
from app.services import google_oauth
from app.services.google_oauth import GoogleOAuthError
from app.services.smtp_client import SmtpSendError

logger = logging.getLogger(__name__)

REFRESH_MARGIN = timedelta(seconds=60)  # refresh slightly before the token actually expires


def is_gmail_oauth(account: EmailAccount) -> bool:
    return account.account_type == AccountType.OAUTH and account.provider == EmailProvider.GMAIL


def _as_delivery_error(error: GoogleOAuthError) -> SmtpSendError:
    return SmtpSendError(error.code, error.message, transient=error.transient)


def _decrypt(value: str | None, what: str) -> str:
    try:
        return decrypt_secret(value or "")
    except DecryptionError:
        raise SmtpSendError(
            "credential_unreadable", f"The stored Gmail {what} could not be read. Reconnect Gmail on the Email Accounts page."
        )


def refresh_tokens(db: Session, account: EmailAccount, *, force: bool = False) -> str:
    """Refresh the access token if needed (or always, with force) and return a valid one."""
    # Lock the account row so parallel workers don't refresh and overwrite each other.
    locked = db.scalar(select(EmailAccount).where(EmailAccount.id == account.id).with_for_update())
    now = datetime.now(timezone.utc)
    if not force and locked.encrypted_oauth_access_token and locked.oauth_token_expires_at and locked.oauth_token_expires_at - REFRESH_MARGIN > now:
        access = _decrypt(locked.encrypted_oauth_access_token, "access token")
        db.commit()  # release the lock
        return access

    if not locked.encrypted_oauth_refresh_token:
        db.rollback()
        raise SmtpSendError("oauth_revoked", "Gmail access has expired. Reconnect Gmail on the Email Accounts page.")
    refresh = _decrypt(locked.encrypted_oauth_refresh_token, "refresh token")
    try:
        tokens = google_oauth.refresh_access_token(refresh)
    except GoogleOAuthError as error:
        db.rollback()
        logger.warning("Gmail token refresh failed account=%s code=%s", locked.id, error.code)
        raise _as_delivery_error(error)

    locked.encrypted_oauth_access_token = encrypt_secret(tokens.access_token)
    if tokens.refresh_token and tokens.refresh_token != refresh:
        locked.encrypted_oauth_refresh_token = encrypt_secret(tokens.refresh_token)
    locked.oauth_token_expires_at = tokens.expires_at
    db.commit()
    logger.info("Refreshed Gmail access token account=%s", locked.id)
    return tokens.access_token


def gmail_raw_message(message: EmailMessage, bcc: list[str]) -> bytes:
    """RFC 5322 bytes for the Gmail API.

    Unlike SMTP (where BCC goes only in the envelope), the Gmail API reads recipients
    from the To/Cc/Bcc headers and removes the Bcc header before delivery, so BCC is
    added here, on a copy, only for this transport.
    """
    outgoing = copy.deepcopy(message)
    if bcc:
        outgoing["Bcc"] = ", ".join(bcc)
    return outgoing.as_bytes(policy=policy.SMTP)  # CRLF line endings


def send_via_gmail(db: Session, account: EmailAccount, message: EmailMessage, bcc: list[str]) -> None:
    raw = gmail_raw_message(message, bcc)
    access = refresh_tokens(db, account)
    try:
        google_oauth.send_raw_message(access, raw)
        return
    except GoogleOAuthError as error:
        if error.code != "token_invalid":
            raise _as_delivery_error(error)
    # The token was rejected before its recorded expiry (e.g. revoked and re-granted): refresh once and retry.
    access = refresh_tokens(db, account, force=True)
    try:
        google_oauth.send_raw_message(access, raw)
    except GoogleOAuthError as error:
        raise _as_delivery_error(error)
