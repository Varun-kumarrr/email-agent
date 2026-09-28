import enum


class SecurityType(str, enum.Enum):
    NONE = "NONE"
    STARTTLS = "STARTTLS"
    SSL_TLS = "SSL_TLS"


class EmailFormat(str, enum.Enum):
    HTML = "HTML"
    PLAIN_TEXT = "PLAIN_TEXT"


class EmailStatus(str, enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"
