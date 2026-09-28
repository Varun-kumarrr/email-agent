from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.config import google_oauth_configured, settings
from app.core.dependencies import CurrentCompany, CurrentUser, DbSession
from app.core.exceptions import ServiceUnavailableError
from app.core.rate_limit import oauth_limiter
from app.models import EmailProvider
from app.schemas.errors import ErrorResponse
from app.services import google_oauth
from app.services.oauth_service import OAuthFlowError, complete_gmail_connection, create_state

router = APIRouter(prefix="/oauth", tags=["OAuth"])


class AuthorizationUrlResponse(BaseModel):
    authorization_url: str


def _frontend_redirect(provider: str, status: str, reason: str | None = None) -> RedirectResponse:
    """Always redirect to the fixed, configured frontend page (never a user-supplied URL)."""
    params = {"oauth": provider, "status": status}
    if reason:
        params["reason"] = reason
    url = f"{settings.FRONTEND_URL.rstrip('/')}/email-accounts?{urlencode(params)}"
    response = RedirectResponse(url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/gmail/authorize",
    response_model=AuthorizationUrlResponse,
    summary="Start connecting a Gmail account (OAuth 2.0)",
    description=(
        "Creates a one-time, expiring state (with PKCE) for the authenticated user and company and "
        "returns Google's consent URL. The frontend sends the browser there; Google then redirects "
        "to /oauth/gmail/callback. Scopes: openid, email, gmail.send."
    ),
    responses={503: {"model": ErrorResponse, "description": "Gmail OAuth is not configured on the server"}},
)
def gmail_authorize(user: CurrentUser, company: CurrentCompany, db: DbSession):
    if not google_oauth_configured(settings):
        raise ServiceUnavailableError("Gmail OAuth is not configured on this server (GOOGLE_CLIENT_ID/SECRET).")
    oauth_limiter.hit(str(company.id))
    state, challenge = create_state(db, user, company, EmailProvider.GMAIL)
    return AuthorizationUrlResponse(authorization_url=google_oauth.build_authorization_url(state, challenge))


@router.get(
    "/gmail/callback",
    summary="Google redirects here after consent (browser redirect, no JWT)",
    description=(
        "Validates and consumes the state, exchanges the code server-side, stores encrypted tokens on a "
        "Gmail OAuth email account, then redirects to the frontend's Email Accounts page with only "
        "`status=success` or `status=error&reason=<code>`."
    ),
    response_class=RedirectResponse,
    status_code=302,
)
def gmail_callback(db: DbSession, state: str | None = None, code: str | None = None, error: str | None = None):
    try:
        result = complete_gmail_connection(db, state=state, code=code, error=error)
    except OAuthFlowError as failure:
        return _frontend_redirect("gmail", "error", failure.reason)
    return _frontend_redirect("gmail", "success", "reconnected" if not result.created else None)
