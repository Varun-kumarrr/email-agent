"""Helpers for placing the saved signature exactly once."""

import re

# A short sign-off line such as "Best regards," / "Thanks!" / "Sincerely,".
_CLOSING_RE = re.compile(
    r"^(?:(?:best|kind|warm|warmest|many)\s+)?(?:regards|wishes|thanks|thank you|sincerely|cheers|"
    r"yours(?: sincerely| truly)?|best)[\s,.!]*$",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip().splitlines())


def is_closing_line(line: str) -> bool:
    return bool(_CLOSING_RE.match(line.strip()))


def signature_has_closing(signature: str) -> bool:
    """True when the signature starts with its own sign-off (e.g. 'Best Regards,')."""
    lines = [line for line in signature.strip().splitlines() if line.strip()]
    return bool(lines) and is_closing_line(lines[0])


def ends_with_signature(body: str, signature: str) -> bool:
    return bool(signature.strip()) and _normalize(body).endswith(_normalize(signature))


def strip_trailing_signature(body: str, signature: str) -> str:
    """Remove the signature if the body already ends with it."""
    if not ends_with_signature(body, signature):
        return body
    normalized = _normalize(body)
    return normalized[: -len(_normalize(signature))].rstrip()


def drop_trailing_closing(body: str) -> str:
    lines = body.rstrip().splitlines()
    if lines and is_closing_line(lines[-1]):
        return "\n".join(lines[:-1]).rstrip()
    return body.rstrip()


def append_signature(body: str, signature: str) -> str:
    """Append the signature unless it is already there.

    If the signature carries its own sign-off, a trailing sign-off in the body
    is removed so the recipient doesn't see "Best regards," twice.
    """
    if ends_with_signature(body, signature):
        return body
    if signature_has_closing(signature):
        body = drop_trailing_closing(body)
    return f"{body.rstrip()}\n\n{signature.strip()}"
