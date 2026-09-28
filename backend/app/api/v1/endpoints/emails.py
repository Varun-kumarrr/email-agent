import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentCompany, CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.models import EmailStatus
from app.repositories.email_history_repository import EmailHistoryRepository
from app.schemas.email import EmailHistoryItem, EmailHistoryPage, SendEmailRequest, SendEmailResponse
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


@router.get(
    "/history",
    response_model=EmailHistoryPage,
    summary="List the company's sent/failed emails (newest first)",
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
