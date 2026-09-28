from fastapi import APIRouter, status

from app.core.dependencies import CurrentCompany, DbSession
from app.schemas.email_config import EmailConfigCreate, EmailConfigResponse, EmailConfigUpdate
from app.services.email_config_service import EmailConfigService, to_response

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
