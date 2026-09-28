import uuid

from fastapi import APIRouter, Response, status

from app.core.dependencies import CurrentCompany, DbSession
from app.schemas.errors import ErrorResponse
from app.schemas.template import (
    TemplateCreate,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.email_account_service import EmailAccountService
from app.services.template_service import BUILTIN_VARIABLES, TemplateService

router = APIRouter(prefix="/email-templates", tags=["Email Templates"])

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Template not found (or belongs to another company)"}}


@router.get("", response_model=list[TemplateResponse], summary="List the company's email templates")
def list_templates(company: CurrentCompany, db: DbSession, active_only: bool = False):
    return TemplateService(db).list(company, active_only=active_only)


@router.get("/builtin-variables", response_model=list[str], summary="Variables filled automatically")
def builtin_variables():
    return list(BUILTIN_VARIABLES)


@router.post(
    "",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an email template",
    description=(
        "Use `{{ variable_name }}` placeholders (letters, digits, underscores). Built-in variables "
        f"({', '.join(BUILTIN_VARIABLES)}) are filled automatically. Expressions and code are rejected."
    ),
    responses={409: {"model": ErrorResponse, "description": "Template name already used"}},
)
def create_template(data: TemplateCreate, company: CurrentCompany, db: DbSession):
    return TemplateService(db).create(company, data)


@router.get("/{template_id}", response_model=TemplateResponse, summary="Get one template", responses=_NOT_FOUND)
def get_template(template_id: uuid.UUID, company: CurrentCompany, db: DbSession):
    return TemplateService(db).get(company, template_id)


@router.patch("/{template_id}", response_model=TemplateResponse, summary="Update a template", responses=_NOT_FOUND)
def update_template(template_id: uuid.UUID, data: TemplateUpdate, company: CurrentCompany, db: DbSession):
    return TemplateService(db).update(company, template_id, data)


@router.delete(
    "/{template_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a template", responses=_NOT_FOUND
)
def delete_template(template_id: uuid.UUID, company: CurrentCompany, db: DbSession):
    TemplateService(db).delete(company, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{template_id}/preview",
    response_model=TemplatePreviewResponse,
    summary="Render a template with variables",
    description="Missing variables stay as `{{ name }}` and are listed, or return 422 when `strict` is true.",
    responses={**_NOT_FOUND, 422: {"model": ErrorResponse, "description": "Missing variables (strict mode)"}},
)
def preview_template(template_id: uuid.UUID, data: TemplatePreviewRequest, company: CurrentCompany, db: DbSession):
    service = TemplateService(db)
    template = service.get(company, template_id)
    accounts = EmailAccountService(db)
    account = accounts.get(company, data.email_account_id) if data.email_account_id else accounts.default_account(company)
    return service.preview(
        company,
        template,
        account=account,
        variables=data.variables,
        recipient_name=data.recipient_name,
        recipient_email=str(data.recipient_email) if data.recipient_email else None,
        strict=data.strict,
    )
