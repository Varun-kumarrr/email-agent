"""Helpers for placing the saved signature exactly once."""


def _normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip().splitlines())


def ends_with_signature(body: str, signature: str) -> bool:
    return bool(signature.strip()) and _normalize(body).endswith(_normalize(signature))


def strip_trailing_signature(body: str, signature: str) -> str:
    """Remove the signature if the body already ends with it."""
    if not ends_with_signature(body, signature):
        return body
    normalized = _normalize(body)
    return normalized[: -len(_normalize(signature))].rstrip()


def append_signature(body: str, signature: str) -> str:
    """Append the signature unless it is already there."""
    if ends_with_signature(body, signature):
        return body
    return f"{body.rstrip()}\n\n{signature.strip()}"
