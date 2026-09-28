import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import HttpUrlStr, PhoneStr, Text


class ServiceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Text(200, min_length=1)
    description: Text(2000) | None = None


class TargetCustomerItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment: Text(200, min_length=1)
    description: Text(2000) | None = None


class ValuePropositionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    statement: Text(1000, min_length=1)


class SocialLinkItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: Text(60, min_length=1) = Field(examples=["LinkedIn"])
    url: HttpUrlStr = Field(examples=["https://www.linkedin.com/company/abctech"])


class CompanyBase(BaseModel):
    name: Text(200, min_length=1) = Field(examples=["ABC Technologies"])
    description: Text(5000, min_length=1) = Field(
        examples=["AI-powered CRM solutions for small and medium-sized businesses."]
    )
    website: HttpUrlStr | None = Field(default=None, examples=["https://www.abctech.com"])
    industry: Text(120) | None = Field(default=None, examples=["Software"])
    location: Text(200) | None = Field(default=None, examples=["Bengaluru, India"])

    contact_person: Text(120) | None = Field(default=None, examples=["Anjali Sharma"])
    contact_email: EmailStr | None = Field(default=None, examples=["anjali@abctech.com"])
    contact_phone: PhoneStr | None = Field(default=None, examples=["+91 98765 43210"])
    address: Text(500) | None = None

    services: list[ServiceItem] = Field(default_factory=list, max_length=50)
    target_customers: list[TargetCustomerItem] = Field(default_factory=list, max_length=50)
    value_propositions: list[ValuePropositionItem] = Field(default_factory=list, max_length=50)
    social_links: list[SocialLinkItem] = Field(default_factory=list, max_length=20)


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(CompanyBase):
    """PUT replaces the whole profile, including the lists."""


class CompanyResponse(CompanyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
