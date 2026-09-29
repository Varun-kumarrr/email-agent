"""Logging setup with a defence-in-depth redaction filter.

The application never logs secrets on purpose; this filter additionally masks
anything that looks like a bearer token, JWT, password or API key in case a
third-party library or a future change logs one by accident.
"""

import logging
import re

_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1[REDACTED]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)((?:password|passwd|pwd|secret|api[_-]?key|x-goog-api-key|token)\s*[=:]\s*)(\S+)"), r"\1[REDACTED]"),
    (re.compile(r"(postgresql(?:\+\w+)?://[^:/\s]+:)[^@\s]+@"), r"\1[REDACTED]@"),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"gsk_[0-9A-Za-z]{20,}"), "[REDACTED_API_KEY]"),  # Groq API keys
]


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


class OAuthQueryRedactingFilter(logging.Filter):
    """Uvicorn's access log records the full request URL. An OAuth callback URL carries the
    authorization code and state in its query string, so drop the query for /oauth/ paths.
    (uvicorn.access args: client_addr, method, full_path, http_version, status_code)"""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path = args[2]
            if "/oauth/" in path and "?" in path:
                record.args = (*args[:2], path.split("?", 1)[0] + "?[redacted]", *args[3:])
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for h in root.handlers for f in h.filters):
        root.addHandler(handler)
    root.setLevel(level)
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, OAuthQueryRedactingFilter) for f in access_logger.filters):
        access_logger.addFilter(OAuthQueryRedactingFilter())
    # httpx logs full request URLs at INFO; keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
