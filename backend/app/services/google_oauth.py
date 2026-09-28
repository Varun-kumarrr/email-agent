"""Google OAuth 2.0 (authorization-code flow with PKCE) and the Gmail API, over plain HTTPS.

Endpoints are Google's official ones. Tokens, authorization codes and the client
secret are only ever sent to Google over HTTPS; they are never logged, and every
error raised here carries a static, safe message (Google's raw error bodies are
not passed on).
"""

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SCOPES = ("openid", "email", GMAIL_SEND_SCOPE)

# Tests replace this with httpx.MockTransport so no request ever reaches Google.
TRANSPORT: httpx.BaseTransport | None = None
TIMEOUT_SECONDS = 20.0


class GoogleOAuthError(Exception):
    """Safe error: `code` is machine-readable, `message` can be shown to users."""

    def __init__(self, code: str, message: str, *, transient: bool = False):
        self.code = code
        self.message = message
        self.transient = transient
        super().__init__(message)


@dataclass
class TokenSet:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    expires_at: datetime
    scopes: list[str]


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, transport=TRANSPORT)


def build_authorization_url(state: str, code_challenge: str) -> str:
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,  # must match the Google Cloud client exactly
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # ask for a refresh token
        "prompt": "consent",  # always return a refresh token, even on reconnect
        "include_granted_scopes": "false",  # only the scopes above, nothing previously granted
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _post_token(data: dict, *, failure_code: str, failure_message: str) -> dict:
    payload = {
        **data,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
    }
    try:
        with _client() as client:
            response = client.post(TOKEN_URL, data=payload, headers={"Accept": "application/json"})
    except httpx.TimeoutException:
        raise GoogleOAuthError("google_timeout", "Google did not respond in time. Please try again.", transient=True)
    except httpx.HTTPError:
        raise GoogleOAuthError("google_unreachable", "Could not reach Google. Please try again.", transient=True)

    if response.status_code >= 500 or response.status_code == 429:
        raise GoogleOAuthError("google_unavailable", "Google is temporarily unavailable. Please try again.", transient=True)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or "access_token" not in body:
        # Log only the OAuth error *code* (e.g. invalid_grant), never the request or response body.
        logger.warning("Google token endpoint rejected the request error=%s status=%s", body.get("error"), response.status_code)
        raise GoogleOAuthError(failure_code, failure_message)
    return body


def _token_set(body: dict, fallback_refresh_token: str | None = None) -> TokenSet:
    expires_in = int(body.get("expires_in") or 3600)
    return TokenSet(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token") or fallback_refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        scopes=(body.get("scope") or "").split(),
    )


def exchange_code(code: str, code_verifier: str) -> TokenSet:
    body = _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        },
        failure_code="token_exchange_failed",
        failure_message="Google rejected the authorization. Please try connecting Gmail again.",
    )
    return _token_set(body)


def refresh_access_token(refresh_token: str) -> TokenSet:
    body = _post_token(
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        failure_code="oauth_revoked",
        failure_message=(
            "Gmail access has expired or was revoked. Reconnect Gmail on the Email Accounts page."
        ),
    )
    # Google normally does not return a new refresh token here; keep using the old one.
    return _token_set(body, fallback_refresh_token=refresh_token)


def fetch_verified_email(access_token: str) -> str:
    try:
        with _client() as client:
            response = client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError:
        raise GoogleOAuthError("google_unreachable", "Could not reach Google. Please try again.", transient=True)
    if response.status_code != 200:
        raise GoogleOAuthError("userinfo_failed", "Could not read the Gmail address from Google.")
    info = response.json()
    email = (info.get("email") or "").strip().lower()
    if not email or info.get("email_verified") is not True:
        raise GoogleOAuthError("email_unverified", "Google did not confirm a verified email address for this account.")
    return email


def send_raw_message(access_token: str, raw_message: bytes) -> str:
    """Send an RFC 5322 message with the Gmail API. Returns Gmail's message id."""
    payload = {"raw": base64.urlsafe_b64encode(raw_message).decode("ascii")}
    try:
        with _client() as client:
            response = client.post(GMAIL_SEND_URL, json=payload, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.TimeoutException:
        raise GoogleOAuthError("timeout", "Timed out contacting the Gmail API.", transient=True)
    except httpx.HTTPError:
        raise GoogleOAuthError("connection_failed", "Could not reach the Gmail API.", transient=True)

    status = response.status_code
    if status == 200:
        return response.json().get("id", "")
    if status == 401:
        raise GoogleOAuthError("token_invalid", "The Gmail access token was rejected.")
    if status == 403:
        raise GoogleOAuthError(
            "gmail_forbidden",
            "Gmail refused to send: the account did not grant permission to send email, or the Gmail API "
            "is not enabled for this Google Cloud project.",
        )
    if status == 400:
        raise GoogleOAuthError("gmail_rejected", "Gmail rejected the message (check the recipient addresses).")
    if status == 429 or status >= 500:
        raise GoogleOAuthError("gmail_unavailable", "Gmail is temporarily unavailable or rate limited.", transient=True)
    logger.warning("Gmail API send failed status=%s", status)
    raise GoogleOAuthError("gmail_error", "The Gmail API returned an error.")
