import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.dependencies import CurrentCompany, CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.models import EmailStatus
from app.repositories.email_history_repository import EmailHistoryRepository
from app.schemas.email import EmailHistoryItem, EmailHistoryPage, SendEmailRequest, SendEmailResponse
from app.schemas.errors import ErrorResponse
from app.services.email_sender import EmailSenderService

router = APIRouter(prefix="/emails", tags=["Emails"])


@router.post(
    "/send",
    response_model=SendEmailResponse,
    summary="Send an email through one of the company's own email accounts",
    description=(
        "The sender is always the selected (or default) account of the authenticated company; there "
        "is no system-wide sender. Applies preferences (sender name, reply-to, format, default CC/BCC, "
        "limits) and the signature, and records the email in the history. In background mode "
        "(EMAIL_DELIVERY_MODE=celery) it returns **202** with status QUEUED right away and a worker "
        "delivers it (poll GET /emails/history/{id}); in sync mode it returns 200 once sent."
    ),
    responses={
        202: {"model": SendEmailResponse, "description": "Queued for background delivery"},
        400: {"model": ErrorResponse, "description": "Too many recipients or inactive account"},
        404: {"model": ErrorResponse, "description": "Company or email account missing"},
        429: {"model": ErrorResponse, "description": "Daily sending limit reached"},
        502: {"model": ErrorResponse, "description": "Delivery failed (sync mode; recorded in history)"},
        503: {"model": ErrorResponse, "description": "Background queue unavailable (recorded in history)"},
    },
)
def send_email(data: SendEmailRequest, company: CurrentCompany, user: CurrentUser, db: DbSession, response: Response):
    result = EmailSenderService(db).send(company, user, data)
    if not result.status.is_final:
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.get(
    "/history",
    response_model=EmailHistoryPage,
    summary="List the company's emails and their delivery status (newest first)",
)
def email_history(
    company: CurrentCompany,
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: EmailStatus | None = None,
):
    items, total = EmailHistoryRepository(db).list_for_company(
        company.id, offset=(page - 1) * page_size, limit=page_size, status=status
    )
    return EmailHistoryPage(
        items=items, total=total, page=page, page_size=page_size, pages=max(math.ceil(total / page_size), 1)
    )


@router.get("/history/{history_id}", response_model=EmailHistoryItem, summary="Get one history record")
def email_history_item(history_id: uuid.UUID, company: CurrentCompany, db: DbSession):
    record = EmailHistoryRepository(db).get_for_company(company.id, history_id)
    if record is None:  # also returned for other companies' records: no existence leak
        raise NotFoundError("Email not found")
    return record
