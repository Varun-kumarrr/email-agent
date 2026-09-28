from fastapi import APIRouter, status

from app.core.dependencies import CurrentCompany, CurrentUser, DbSession
from app.schemas.email_config import (
    EmailConfigCreate,
    EmailConfigResponse,
    EmailConfigUpdate,
    SmtpTestRequest,
    SmtpTestResponse,
)
from app.services.email_config_service import EmailConfigService, SmtpTestService, to_response

router = APIRouter(prefix="/email-config", tags=["Email Configuration"])


@router.post(
    "",
    response_model=EmailConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save the company's SMTP account",
    description="The password is encrypted at rest and is never returned by any endpoint.",
)
def create_email_config(data: EmailConfigCreate, company: CurrentCompany, db: DbSession):
    return to_response(EmailConfigService(db).create(company, data))


@router.get(
    "",
    response_model=EmailConfigResponse,
    summary="Get the company's SMTP account (without the password)",
)
def get_email_config(company: CurrentCompany, db: DbSession):
    return to_response(EmailConfigService(db).get(company))


@router.put(
    "",
    response_model=EmailConfigResponse,
    summary="Update the company's SMTP account",
    description="Omit `password` to keep the stored password; supply it to replace it.",
)
def update_email_config(data: EmailConfigUpdate, company: CurrentCompany, db: DbSession):
    return to_response(EmailConfigService(db).update(company, data))


@router.post(
    "/test",
    response_model=SmtpTestResponse,
    summary="Send a test email through the company's SMTP account",
    description=(
        "Connects with the configured security mode, authenticates and sends a test email. "
        "Always returns 200 with `success` true/false and a safe message; credentials and "
        "stack traces are never included."
    ),
)
def test_email_config(data: SmtpTestRequest, company: CurrentCompany, user: CurrentUser, db: DbSession):
    return SmtpTestService(db).run(company, data.recipient, user)
