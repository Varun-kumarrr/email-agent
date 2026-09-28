import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72, examples=["Str0ngPassw0rd"])
    name: str = Field(min_length=1, max_length=120, examples=["Anjali Sharma"])

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password is too long")  # bcrypt only uses the first 72 bytes
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one letter and one number")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """Public user representation. Deliberately has no password/hash field."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    has_company: bool = False
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
    user: UserResponse
