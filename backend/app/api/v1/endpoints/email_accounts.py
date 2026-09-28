import uuid

from fastapi import APIRouter, Response, status

from app.core.dependencies import CurrentCompany, DbSession
from app.schemas.email_account import (
    EmailAccountCreate,
    EmailAccountResponse,
    EmailAccountTestRequest,
    EmailAccountUpdate,
)
from app.schemas.email_config import SmtpTestResponse
from app.schemas.errors import ErrorResponse
from app.services.email_account_service import EmailAccountService, to_response
from app.services.email_config_service import run_account_test

router = APIRouter(prefix="/email-accounts", tags=["Email Accounts"])

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Account not found (or belongs to another company)"}}


@router.get("", response_model=list[EmailAccountResponse], summary="List the company's email accounts")
def list_accounts(company: CurrentCompany, db: DbSession):
    return [to_response(a) for a in EmailAccountService(db).list(company)]


@router.post(
    "",
    response_model=EmailAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an SMTP email account (Gmail, Outlook or any public SMTP server)",
    description=(
        "For provider GMAIL/OUTLOOK, host/port/security default to the provider's SMTP settings. "
        "The password is encrypted at rest and never returned. OAuth accounts are added through "
        "the OAuth connect flow instead."
    ),
    responses={409: {"model": ErrorResponse, "description": "Account with this address already exists"}},
)
def create_account(data: EmailAccountCreate, company: CurrentCompany, db: DbSession):
    return to_response(EmailAccountService(db).create_smtp(company, data))


@router.get("/{account_id}", response_model=EmailAccountResponse, summary="Get one email account", responses=_NOT_FOUND)
def get_account(account_id: uuid.UUID, company: CurrentCompany, db: DbSession):
    return to_response(EmailAccountService(db).get(company, account_id))


@router.patch(
    "/{account_id}",
    response_model=EmailAccountResponse,
    summary="Update an email account",
    description="Partial update. Omit `password` to keep it. Deactivating the default account promotes another.",
    responses=_NOT_FOUND,
)
def update_account(account_id: uuid.UUID, data: EmailAccountUpdate, company: CurrentCompany, db: DbSession):
    return to_response(EmailAccountService(db).update(company, account_id, data))


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an email account",
    description="History records keep the sender address; deleting the default promotes another account.",
    responses=_NOT_FOUND,
)
def delete_account(account_id: uuid.UUID, company: CurrentCompany, db: DbSession):
    EmailAccountService(db).delete(company, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{account_id}/set-default",
    response_model=EmailAccountResponse,
    summary="Make this account the company's default sender",
    responses=_NOT_FOUND,
)
def set_default_account(account_id: uuid.UUID, company: CurrentCompany, db: DbSession):
    return to_response(EmailAccountService(db).set_default(company, account_id))


@router.post(
    "/{account_id}/test",
    response_model=SmtpTestResponse,
    summary="Send a test email through this account",
    description="Always 200 with `success` true/false and a safe message; no credentials or raw server output.",
    responses=_NOT_FOUND,
)
def test_account(account_id: uuid.UUID, data: EmailAccountTestRequest, company: CurrentCompany, db: DbSession):
    account = EmailAccountService(db).get(company, account_id)
    return run_account_test(db, account, str(data.recipient))
