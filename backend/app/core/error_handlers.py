"""Exception handlers producing one consistent JSON error shape:

    {"error": {"code": "...", "message": "...", "details": ...}}

Clients never receive stack traces, SQL, submitted secrets or internal messages.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError

logger = logging.getLogger("app.errors")

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


def error_response(status_code: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
        headers=headers,
    )


async def app_error_handler(request: Request, exc: AppError):
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return error_response(
        exc.status_code, _HTTP_CODES.get(exc.status_code, "http_error"), message, headers=getattr(exc, "headers", None)
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    # FastAPI's default 422 echoes the submitted value ("input"), which could be a
    # password. Return only the location and message of each problem.
    details = [
        {"field": ".".join(str(part) for part in err["loc"] if part != "body"), "message": err["msg"]}
        for err in exc.errors()
    ]
    return error_response(422, "validation_error", "Request validation failed", details)


async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("Integrity error on %s %s", request.method, request.url.path)
    return error_response(409, "conflict", "The request conflicts with existing data")


async def database_error_handler(request: Request, exc: SQLAlchemyError):
    # Engine uses hide_parameters=True, so bound values (e.g. hashes) are not in the log.
    logger.error("Database error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    if isinstance(exc, OperationalError):
        return error_response(503, "database_unavailable", "The database is temporarily unavailable")
    return error_response(500, "internal_error", "An unexpected error occurred")


async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "internal_error", "An unexpected error occurred")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
