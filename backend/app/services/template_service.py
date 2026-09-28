"""Reusable email templates: CRUD (company-scoped), built-in variables and safe rendering."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, BadRequestError, ConflictError, NotFoundError
from app.models import Company, EmailAccount, EmailFormat, EmailTemplate
from app.schemas.template import TemplateCreate, TemplatePreviewResponse, TemplateUpdate
from app.utils.template_render import extract_variables, render

# Filled automatically from the company profile, sender account and recipient.
BUILTIN_VARIABLES = (
    "company_name",
    "company_website",
    "contact_person",
    "sender_name",
    "sender_email",
    "recipient_name",
    "recipient_email",
)


class MissingTemplateVariables(AppError):
    status_code = 422
    code = "missing_template_variables"
    message = "Some template variables have no value"


def builtin_values(
    company: Company,
    account: EmailAccount | None,
    *,
    sender_name: str | None = None,
    recipient_name: str | None = None,
    recipient_email: str | None = None,
) -> dict[str, str]:
    values = {
        "company_name": company.name,
        "company_website": company.website,
        "contact_person": company.contact_person,
        "sender_name": sender_name or (account.sender_name if account else None) or company.contact_person,
        "sender_email": account.email_address if account else company.contact_email,
        "recipient_name": recipient_name,
        "recipient_email": recipient_email,
    }
    return {k: v for k, v in values.items() if v}


def render_template(
    template: EmailTemplate, values: dict[str, str]
) -> tuple[str, str, list[str]]:
    """Render subject and body. Returns (subject, body, missing_variable_names)."""
    subject, missing_subject = render(template.subject_template, values, single_line=True)
    body, missing_body = render(
        template.body_template, values, escape_html=template.content_type == EmailFormat.HTML
    )
    missing = list(dict.fromkeys(missing_subject + missing_body))
    return subject, body, missing


class TemplateService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, company: Company, *, active_only: bool = False) -> list[EmailTemplate]:
        query = select(EmailTemplate).where(EmailTemplate.company_id == company.id)
        if active_only:
            query = query.where(EmailTemplate.is_active.is_(True))
        return list(self.db.scalars(query.order_by(EmailTemplate.name)))

    def get(self, company: Company, template_id: uuid.UUID) -> EmailTemplate:
        template = self.db.scalar(
            select(EmailTemplate).where(EmailTemplate.id == template_id, EmailTemplate.company_id == company.id)
        )
        if template is None:
            raise NotFoundError("Email template not found")
        return template

    def get_active(self, company: Company, template_id: uuid.UUID) -> EmailTemplate:
        template = self.get(company, template_id)
        if not template.is_active:
            raise BadRequestError("This template is inactive. Activate it before using it.")
        return template

    def create(self, company: Company, data: TemplateCreate) -> EmailTemplate:
        template = EmailTemplate(company_id=company.id, **data.model_dump())
        template.variables = extract_variables(template.subject_template, template.body_template)
        self.db.add(template)
        self._commit()
        return template

    def update(self, company: Company, template_id: uuid.UUID, data: TemplateUpdate) -> EmailTemplate:
        template = self.get(company, template_id)
        changes = data.model_dump(exclude_unset=True)
        for required in ("name", "subject_template", "body_template", "content_type", "is_active"):
            if required in changes and changes[required] is None:
                raise BadRequestError(f"{required} cannot be null")
        for field, value in changes.items():
            setattr(template, field, value)
        template.variables = extract_variables(template.subject_template, template.body_template)
        self._commit()
        return template

    def delete(self, company: Company, template_id: uuid.UUID) -> None:
        self.db.delete(self.get(company, template_id))
        self.db.commit()

    def preview(
        self,
        company: Company,
        template: EmailTemplate,
        *,
        account: EmailAccount | None,
        variables: dict[str, str],
        recipient_name: str | None,
        recipient_email: str | None,
        strict: bool,
    ) -> TemplatePreviewResponse:
        values = builtin_values(company, account, recipient_name=recipient_name, recipient_email=recipient_email)
        values.update({k: v for k, v in variables.items() if v.strip()})  # user values win
        subject, body, missing = render_template(template, values)
        if strict and missing:
            raise MissingTemplateVariables(details={"missing_variables": missing})
        used = {k: v for k, v in values.items() if k in template.variables}
        return TemplatePreviewResponse(
            subject=subject, body=body, content_type=template.content_type, variables_used=used, missing_variables=missing
        )

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ConflictError("A template with this name already exists.")
