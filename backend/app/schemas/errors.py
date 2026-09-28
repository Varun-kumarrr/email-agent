from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["Company profile not found. Create your company profile first."])
    details: Any = None


class ErrorResponse(BaseModel):
    """Shape of every error response."""

    error: ErrorBody


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or expired token"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
    500: {"model": ErrorResponse, "description": "Unexpected server error"},
}
