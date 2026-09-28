import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import EmailFormat
from app.schemas.common import Text
from app.utils.template_render import MAX_VALUE_LENGTH, TemplateSyntaxError, validate_template


def _check_template(value: str) -> str:
    try:
        validate_template(value)
    except TemplateSyntaxError as error:
        raise ValueError(str(error)) from None
    return value


def _check_subject(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("Subject must be a single line")
    return _check_template(value)


SubjectTemplate = Annotated[Text(300, min_length=1), AfterValidator(_check_subject)]
BodyTemplate = Annotated[Text(20000, min_length=1), AfterValidator(_check_template)]

EXAMPLE_BODY = (
    "Hi {{recipient_name}},\n\nI'm {{sender_name}} from {{company_name}}. "
    "I'd love to show you how {{product_name}} could help your team.\n\n"
    "Would {{meeting_date}} work for a short call?"
)


class TemplateCreate(BaseModel):
    name: Text(120, min_length=1) = Field(examples=["Cold intro"])
    description: Text(1000) | None = None
    category: Text(60) | None = Field(default=None, examples=["Sales"])
    subject_template: SubjectTemplate = Field(examples=["{{company_name}}: {{product_name}} for your team"])
    body_template: BodyTemplate = Field(examples=[EXAMPLE_BODY])
    content_type: EmailFormat = EmailFormat.PLAIN_TEXT
    is_active: bool = True


class TemplateUpdate(BaseModel):
    """Partial update (PATCH)."""

    name: Text(120, min_length=1) | None = None
    description: Text(1000) | None = None
    category: Text(60) | None = None
    subject_template: SubjectTemplate | None = None
    body_template: BodyTemplate | None = None
    content_type: EmailFormat | None = None
    is_active: bool | None = None


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    category: str | None
    subject_template: str
    body_template: str
    content_type: EmailFormat
    variables: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


def _check_variables(values: dict[str, str]) -> dict[str, str]:
    if len(values) > 30:
        raise ValueError("At most 30 variables")
    for key, value in values.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key):
            raise ValueError(f"Invalid variable name: {key[:40]}")
        if len(value) > MAX_VALUE_LENGTH:
            raise ValueError(f"Value for {key} is too long")
    return values


TemplateVariables = Annotated[dict[str, str], AfterValidator(_check_variables)]


class TemplatePreviewRequest(BaseModel):
    variables: TemplateVariables = Field(default_factory=dict, examples=[{"product_name": "CRM", "meeting_date": "Tuesday"}])
    recipient_name: Text(120) | None = None
    recipient_email: EmailStr | None = None
    email_account_id: uuid.UUID | None = Field(default=None, description="Sender identity for {{sender_name}}.")
    strict: bool = Field(default=False, description="If true, missing variables return 422 instead of staying unfilled.")


class TemplatePreviewResponse(BaseModel):
    subject: str
    body: str
    content_type: EmailFormat
    variables_used: dict[str, str] = Field(description="Values substituted (built-in values plus yours).")
    missing_variables: list[str] = Field(description="Placeholders left unfilled.")

    @field_validator("variables_used")
    @classmethod
    def _sorted(cls, value):
        return dict(sorted(value.items()))
