from fastapi import APIRouter

from app.core.dependencies import CurrentCompany, CurrentUser, DbSession
from app.schemas.email import SendEmailRequest, SendEmailResponse
from app.services.email_sender import EmailSenderService

router = APIRouter(prefix="/emails", tags=["Emails"])


@router.post(
    "/send",
    response_model=SendEmailResponse,
    summary="Send an email through the company's own SMTP account",
    description=(
        "The sender is always the authenticated company's configured SMTP address; there is no "
        "system-wide sender. Applies preferences (sender name, reply-to, format, default CC/BCC, "
        "limits) and the signature, retries transient SMTP errors, and records the attempt in the "
        "email history."
    ),
    responses={
        400: {"description": "Too many recipients"},
        404: {"description": "Company or SMTP configuration missing"},
        429: {"description": "Daily sending limit reached"},
        502: {"description": "SMTP delivery failed (recorded in history)"},
    },
)
def send_email(data: SendEmailRequest, company: CurrentCompany, user: CurrentUser, db: DbSession):
    return EmailSenderService(db).send(company, user, data)
