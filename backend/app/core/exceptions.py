"""Application exceptions. Services raise these; handlers turn them into JSON errors.

Every error response has the same shape:

    {"error": {"code": "not_found", "message": "Company profile not found", "details": null}}

Messages are always safe to show to users: no stack traces, SQL, or secrets.
"""

from typing import Any


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"
    message: str = "Bad request"

    def __init__(self, message: str | None = None, *, details: Any = None, headers: dict | None = None):
        self.message = message or self.message
        self.details = details
        self.headers = headers
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication required"

    def __init__(self, message: str | None = None, **kwargs):
        kwargs.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kwargs)


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "You do not have permission to perform this action"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Resource already exists"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Sending limit reached"


class EmailDeliveryError(AppError):
    status_code = 502
    code = "email_send_failed"
    message = "The email could not be sent"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "An external service is unavailable"
