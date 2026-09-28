"""Thin wrapper around smtplib that speaks the three security modes and turns
low-level failures into safe, user-facing errors.

Credentials are passed per call from the company's own configuration; there is
no global/system SMTP account anywhere in the application.
"""

import ipaddress
import logging
import smtplib
import socket
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage

from app.core.config import settings
from app.models.enums import SecurityType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmtpCredentials:
    host: str
    port: int
    username: str
    password: str = field(repr=False)  # excluded from repr so it cannot leak via logs
    security_type: SecurityType


class SmtpSendError(Exception):
    """A failure with a message that is safe to show users and store in history."""

    def __init__(self, code: str, message: str, *, transient: bool = False):
        self.code = code
        self.message = message
        self.transient = transient  # worth retrying (timeouts, temporary 4xx replies)
        super().__init__(message)


def classify_error(exc: BaseException) -> SmtpSendError:
    """Map an exception to a safe error. Never includes the raw exception text,
    which can contain server responses, usernames or other details."""
    if isinstance(exc, SmtpSendError):
        return exc
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return SmtpSendError(
            "auth_failed",
            "SMTP authentication failed. Check the username and password (many providers require an app password).",
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return SmtpSendError("recipient_refused", "The SMTP server rejected the recipient address.")
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return SmtpSendError(
            "sender_refused", "The SMTP server rejected the sender address. It must match the SMTP account."
        )
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return SmtpSendError(
            "feature_unsupported",
            "The SMTP server does not support a required feature (for example STARTTLS). "
            "Check the security type and port.",
        )
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return SmtpSendError("disconnected", "The SMTP server closed the connection unexpectedly.", transient=True)
    if isinstance(exc, smtplib.SMTPConnectError):
        return SmtpSendError("connect_failed", "The SMTP server refused the connection.", transient=True)
    if isinstance(exc, smtplib.SMTPResponseException):
        transient = 400 <= exc.smtp_code < 500
        return SmtpSendError(
            "smtp_error", f"The SMTP server returned an error (code {exc.smtp_code}).", transient=transient
        )
    if isinstance(exc, smtplib.SMTPException):
        return SmtpSendError("smtp_error", "An SMTP error occurred while sending.")
    if isinstance(exc, ssl.SSLCertVerificationError):
        return SmtpSendError("tls_certificate", "The SMTP server's TLS certificate could not be verified.")
    if isinstance(exc, ssl.SSLError):
        return SmtpSendError(
            "tls_failed",
            "TLS/SSL negotiation failed. Check the security type matches the port "
            "(usually 465 = SSL/TLS, 587 = STARTTLS, 25 = NONE).",
        )
    if isinstance(exc, socket.gaierror):
        return SmtpSendError("invalid_host", "The SMTP host could not be found. Check the host name.")
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return SmtpSendError(
            "timeout", "Timed out connecting to the SMTP server. Check the host, port and firewall.", transient=True
        )
    if isinstance(exc, ConnectionRefusedError):
        return SmtpSendError("connection_refused", "Connection refused. Check the SMTP host and port.")
    if isinstance(exc, OSError):
        return SmtpSendError("connection_failed", "Could not connect to the SMTP server.", transient=True)
    return SmtpSendError("unknown_error", "Unexpected error while sending email.")


def ensure_public_host(host: str, port: int) -> None:
    """Refuse hosts that resolve to private, loopback, link-local or reserved addresses.

    Stops users from pointing "their SMTP server" at internal services (SSRF).
    Note: a hostile DNS server could still change the answer between this check
    and the connection (DNS rebinding); network egress rules are the real fix.
    """
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise classify_error(exc) from None
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise SmtpSendError(
                "host_not_allowed", "This SMTP host resolves to a private or internal address, which is not allowed."
            )


def _open_connection(creds: SmtpCredentials, timeout: float) -> smtplib.SMTP:
    if not settings.SMTP_ALLOW_PRIVATE_HOSTS:
        ensure_public_host(creds.host, creds.port)
    context = ssl.create_default_context()  # verifies certificates and host names
    if creds.security_type == SecurityType.SSL_TLS:
        return smtplib.SMTP_SSL(creds.host, creds.port, timeout=timeout, context=context)

    server = smtplib.SMTP(creds.host, creds.port, timeout=timeout)
    if creds.security_type == SecurityType.STARTTLS:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
    return server


def send_message(
    creds: SmtpCredentials,
    message: EmailMessage,
    recipients: list[str] | None = None,
    timeout: float | None = None,
) -> None:
    """Send one message through the given SMTP account. Raises SmtpSendError.

    `recipients` is the full envelope list (To + CC + BCC). BCC addresses are
    passed only here, never as a header, so other recipients cannot see them.
    """
    server = None
    try:
        server = _open_connection(creds, timeout or settings.SMTP_TIMEOUT_SECONDS)
        server.ehlo_or_helo_if_needed()
        if creds.username and creds.password:
            if server.has_extn("auth"):
                server.login(creds.username, creds.password)
            else:
                # Relays that don't offer AUTH (internal port-25 relays, local dev servers).
                # If the server actually requires auth it will reject the message below.
                logger.info("SMTP server host=%s does not advertise AUTH; sending without login", creds.host)
        server.send_message(message, to_addrs=recipients)
    except Exception as exc:
        error = classify_error(exc)
        # Log only the safe code and exception type — never credentials or raw server text.
        logger.warning("SMTP send failed host=%s code=%s type=%s", creds.host, error.code, type(exc).__name__)
        raise error from None
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass
