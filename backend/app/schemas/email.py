import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import EmailFormat, EmailStatus
from app.schemas.preferences import EmailList


def _single_line(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("Subject must be a single line")
    value = value.strip()
    if not value:
        raise ValueError("Subject must not be blank")
    return value


Subject = Annotated[str, Field(min_length=1, max_length=300), AfterValidator(_single_line)]


class SendEmailRequest(BaseModel):
    recipient: EmailStr = Field(examples=["priya@smallbiz.in"])
    subject: Subject = Field(examples=["Less manual sales work for your business"])
    body: str = Field(min_length=1, max_length=50000, examples=["Hi Priya,\n\n...\n\nBest regards,"])
    format: EmailFormat | None = Field(default=None, description="Defaults to the preference setting.")
    cc: EmailList | None = Field(default=None, description="Omit to use default CC from preferences; [] for none.")
    bcc: EmailList | None = Field(default=None, description="Omit to use default BCC from preferences; [] for none.")
    append_signature: bool | None = Field(
        default=None,
        description="Omit to follow the signature's 'append automatically' setting; true/false to override.",
    )
    email_account_id: uuid.UUID | None = Field(
        default=None,
        description="Email account to send from (must belong to your company and be active). "
        "Omit to use the company's default account.",
    )


class SendEmailResponse(BaseModel):
    id: uuid.UUID = Field(description="Email history record ID.")
    status: EmailStatus
    message: str
    email_account_id: uuid.UUID = Field(description="The account the email was sent from.")
    sender_email: EmailStr
    sender_name: str | None
    recipient: EmailStr
    cc: list[str]
    bcc: list[str]
    subject: str
    format: EmailFormat
    signature_appended: bool
    attempts: int
    sent_at: datetime | None
    task_id: str | None = Field(default=None, description="Background job id (background delivery mode).")


class EmailHistoryItem(BaseModel):
    """A send attempt. Contains no credentials, tokens or keys."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email_account_id: uuid.UUID | None = Field(description="Null if the account was deleted later.")
    sender_email: str
    sender_name: str | None
    reply_to: str | None = None
    recipient: str
    cc: list[str]
    bcc: list[str]
    subject: str
    body: str
    email_format: EmailFormat
    status: EmailStatus = Field(description="QUEUED, SENDING, RETRYING, SENT or FAILED.")
    error_message: str | None = Field(description="Safe failure reason (no secrets or raw server output).")
    error_code: str | None = None
    attempts: int
    created_at: datetime
    last_attempt_at: datetime | None = None
    sent_at: datetime | None
    is_test: bool = Field(default=False, description="True for an email sent by an account's Test action.")


class EmailHistoryPage(BaseModel):
    items: list[EmailHistoryItem]
    total: int
    page: int
    page_size: int
    pages: int
