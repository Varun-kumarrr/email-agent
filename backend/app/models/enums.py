import enum


class SecurityType(str, enum.Enum):
    NONE = "NONE"
    STARTTLS = "STARTTLS"
    SSL_TLS = "SSL_TLS"


class EmailFormat(str, enum.Enum):
    HTML = "HTML"
    PLAIN_TEXT = "PLAIN_TEXT"


class EmailStatus(str, enum.Enum):
    QUEUED = "QUEUED"  # recorded, waiting for a worker (background mode)
    SENDING = "SENDING"  # a delivery attempt is in progress
    RETRYING = "RETRYING"  # a transient error occurred; another attempt is scheduled
    SENT = "SENT"
    FAILED = "FAILED"

    @property
    def is_final(self) -> bool:
        return self in (EmailStatus.SENT, EmailStatus.FAILED)


class EmailProvider(str, enum.Enum):
    """Who operates the mailbox."""

    GMAIL = "GMAIL"
    OUTLOOK = "OUTLOOK"
    GENERIC = "GENERIC"


class AccountType(str, enum.Enum):
    """How the application authenticates to the mailbox."""

    SMTP = "SMTP"  # host/port/username/password (or app password)
    OAUTH = "OAUTH"  # OAuth 2.0 tokens (Gmail API / Microsoft Graph)
