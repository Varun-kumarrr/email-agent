import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.models.enums import SecurityType
from app.schemas.common import Text

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def _validate_host(value: str) -> str:
    value = value.strip().lower()
    if not _HOSTNAME_RE.match(value):
        raise ValueError("SMTP host must be a hostname such as smtp.gmail.com (no scheme or path)")
    return value


SmtpHost = Annotated[str, AfterValidator(_validate_host)]
SmtpPort = Annotated[int, Field(ge=1, le=65535, examples=[587])]
# SecretStr keeps the password masked in repr(), logs and tracebacks.
SmtpPassword = Annotated[SecretStr, Field(min_length=1, max_length=512)]


class EmailConfigBase(BaseModel):
    email: EmailStr = Field(examples=["anjali@abctech.com"])
    smtp_host: SmtpHost = Field(examples=["smtp.gmail.com"])
    smtp_port: SmtpPort
    username: Text(255, min_length=1) = Field(examples=["anjali@abctech.com"])
    security_type: SecurityType = Field(examples=[SecurityType.STARTTLS])
    sender_name: Text(120, min_length=1) = Field(examples=["Anjali from ABC Technologies"])
    reply_to: EmailStr | None = Field(default=None, examples=["sales@abctech.com"])


class EmailConfigCreate(EmailConfigBase):
    password: SmtpPassword = Field(description="SMTP password or app password. Write-only.")


class EmailConfigUpdate(EmailConfigBase):
    password: SmtpPassword | None = Field(
        default=None,
        description="Write-only. Omit (or send null) to keep the currently stored password.",
    )


class EmailConfigResponse(EmailConfigBase):
    """Never contains the password — only whether one is configured."""

    model_config = ConfigDict(from_attributes=True)

    password_configured: bool
    last_tested_at: datetime | None = None
    last_test_success: bool | None = None
    updated_at: datetime
