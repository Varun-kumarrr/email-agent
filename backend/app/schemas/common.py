"""Reusable validated field types."""

import re
from typing import Annotated

from pydantic import AfterValidator, AnyHttpUrl, BeforeValidator, Field, TypeAdapter

_http_url = TypeAdapter(AnyHttpUrl)
_PHONE_RE = re.compile(r"^\+?[0-9 ()\-.]{7,25}$")


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _normalize_url(value):
    """Accept 'www.example.com' by assuming https, then validate as an http(s) URL."""
    if not isinstance(value, str):
        return value
    value = value.strip()
    if value and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        value = f"https://{value}"
    return str(_http_url.validate_python(value))


def _validate_phone(value: str) -> str:
    if not _PHONE_RE.match(value) or sum(c.isdigit() for c in value) < 7:
        raise ValueError("Invalid phone number")
    return value


def _not_blank(value: str) -> str:
    if not value:
        raise ValueError("Must not be blank")
    return value


def Text(max_length: int, min_length: int = 0):
    """A trimmed string with length limits (and non-blank when min_length > 0)."""
    validators = [BeforeValidator(_strip), Field(min_length=min_length, max_length=max_length)]
    if min_length:
        validators.append(AfterValidator(_not_blank))
    return Annotated[str, *validators]


HttpUrlStr = Annotated[str, BeforeValidator(_normalize_url), Field(max_length=500)]
PhoneStr = Annotated[str, BeforeValidator(_strip), AfterValidator(_validate_phone)]
