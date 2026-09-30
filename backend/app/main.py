from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.core.config import settings, validate_production_settings
from app.core.dependencies import DbSession
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging

configure_logging(settings.LOG_LEVEL)
validate_production_settings(settings)

DESCRIPTION = """
Backend for the **Email Agent — Profile & Email Configuration Module**.

A company sets up its profile and its **own SMTP account**; an AI agent drafts
emails grounded in that profile; the user reviews/edits the draft and sends it
through the company's SMTP account. Every send is recorded in the history.

### Authentication
1. `POST /api/v1/auth/register` → create an account.
2. `POST /api/v1/auth/login` → receive a JWT `access_token`.
3. Send `Authorization: Bearer <access_token>` on every other request.
   In Swagger, click **Authorize** and paste the token.

### Data isolation
All company data is resolved from the token's user. No endpoint accepts a
company or user ID, so one company can never access another company's data.

### Secrets
SMTP passwords are write-only (encrypted at rest; responses only show
`password_configured`). Validation errors never echo submitted values.

### Errors
Every error has the shape `{"error": {"code", "message", "details"}}`.
"""

TAGS = [
    {"name": "Health", "description": "Service status."},
    {"name": "Authentication", "description": "Register, log in (JWT) and fetch the current user."},
    {"name": "Company Profile", "description": "The company information used as AI context."},
    {"name": "Email Configuration", "description": "The company's own SMTP account and connection test."},
    {"name": "Email Signature", "description": "Reusable signature, optionally appended automatically."},
    {"name": "Email Preferences", "description": "Sender overrides, format, limits, default CC/BCC."},
    {"name": "AI Email Agent", "description": "Generate an editable email draft from the company context."},
    {"name": "Emails", "description": "Send via the company's SMTP account and view history."},
]

app = FastAPI(
    title="Email Agent API",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=TAGS,
    swagger_ui_parameters={"persistAuthorization": True},
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.path.startswith("/api/"):
        # API responses can contain personal data: never cache them.
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# Only the configured frontend origins may call the API from a browser.
# A wildcard is never used: origins come from ALLOWED_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in settings.ALLOWED_ORIGINS if origin != "*"],
    allow_credentials=False,  # auth uses the Authorization header, not cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=600,
)

register_exception_handlers(app)
app.include_router(api_router)


@app.get("/", tags=["Health"], summary="Health check")
def read_root():
    return {"message": "Email Agent API is running"}


@app.get(
    "/health",
    tags=["Health"],
    summary="Readiness check (API + database, + email queue in background mode)",
    description=(
        "Used by Docker health checks. Returns 503 if the database is unreachable, or, when "
        "EMAIL_DELIVERY_MODE=celery, if the Redis email queue is unreachable (`queue` field). "
        "`GET /` is the dependency-free liveness check."
    ),
)
def health(db: DbSession):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unreachable"})
    if settings.EMAIL_DELIVERY_MODE != "celery":
        return {"status": "ok", "database": "ok"}  # no queue is used in sync mode
    from app.worker.celery_app import broker_reachable  # only imported when background delivery is on

    if not broker_reachable():
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "ok", "queue": "unreachable"})
    return {"status": "ok", "database": "ok", "queue": "ok"}
