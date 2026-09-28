import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

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


class SendEmailResponse(BaseModel):
    id: uuid.UUID = Field(description="Email history record ID.")
    status: EmailStatus
    message: str
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
