from enum import Enum

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import Text


class Tone(str, Enum):
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    FORMAL = "formal"
    PERSUASIVE = "persuasive"
    CONCISE = "concise"


class GenerateEmailRequest(BaseModel):
    recipient_name: Text(120, min_length=1) = Field(examples=["Priya Mehta"])
    recipient_email: EmailStr = Field(examples=["priya@smallbiz.in"])
    purpose: Text(2000, min_length=1) = Field(
        examples=["Write a professional cold email introducing our CRM to a small business owner."]
    )
    tone: Tone = Tone.PROFESSIONAL
    additional_instructions: Text(2000) | None = Field(default=None, examples=["Keep it under 150 words."])


class GenerateEmailResponse(BaseModel):
    subject: str
    body: str
    provider: str = Field(description="Which LLM provider produced the email (e.g. gemini, mock).")
    fallback_used: bool = Field(
        default=False, description="True if the real provider failed and the mock provider was used."
    )
    warning: str | None = None
