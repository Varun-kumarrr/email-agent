from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Text

EXAMPLE_SIGNATURE = (
    "Best Regards,\nAnjali\nBusiness Development Manager\nABC Technologies\n"
    "Email: anjali@abctech.com\nPhone: +91 XXXXX XXXXX\nWebsite: www.abctech.com"
)


class SignatureBase(BaseModel):
    signature_text: Text(2000, min_length=1) = Field(examples=[EXAMPLE_SIGNATURE])
    enabled: bool = True
    append_automatically: bool = Field(
        default=True, description="Append this signature to every outgoing email automatically."
    )


class SignatureCreate(SignatureBase):
    pass


class SignatureUpdate(SignatureBase):
    pass


class SignatureResponse(SignatureBase):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime
