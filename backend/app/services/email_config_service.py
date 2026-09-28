from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.encryption import DecryptionError, decrypt_secret, encrypt_secret
from app.core.exceptions import ConflictError, NotFoundError
from app.models import Company, EmailConfiguration
from app.schemas.email_config import EmailConfigCreate, EmailConfigResponse, EmailConfigUpdate, SmtpTestResponse
from app.services import smtp_client
from app.services.smtp_client import SmtpCredentials, SmtpSendError

_FIELDS = ("email", "smtp_host", "smtp_port", "username", "security_type", "sender_name", "reply_to")


def to_response(config: EmailConfiguration) -> EmailConfigResponse:
    return EmailConfigResponse(
        email=config.email,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        username=config.username,
        security_type=config.security_type,
        sender_name=config.sender_name,
        reply_to=config.reply_to,
        password_configured=bool(config.encrypted_password),
        last_tested_at=config.last_tested_at,
        last_test_success=config.last_test_success,
        updated_at=config.updated_at,
    )


class EmailConfigService:
    def __init__(self, db: Session):
        self.db = db

    def find(self, company: Company) -> EmailConfiguration | None:
        return self.db.scalar(
            select(EmailConfiguration).where(EmailConfiguration.company_id == company.id)
        )

    def get(self, company: Company) -> EmailConfiguration:
        config = self.find(company)
        if config is None:
            raise NotFoundError("Email configuration not found. Configure your SMTP account first.")
        return config

    def create(self, company: Company, data: EmailConfigCreate) -> EmailConfiguration:
        if self.find(company) is not None:
            raise ConflictError("Email configuration already exists. Use PUT to update it.")
        config = EmailConfiguration(
            company_id=company.id,
            encrypted_password=encrypt_secret(data.password.get_secret_value()),
            **{field: getattr(data, field) for field in _FIELDS},
        )
        self.db.add(config)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ConflictError("Email configuration already exists.")
        return config

    def update(self, company: Company, data: EmailConfigUpdate) -> EmailConfiguration:
        config = self.get(company)
        connection_changed = any(
            getattr(config, f) != getattr(data, f)
            for f in ("smtp_host", "smtp_port", "username", "security_type")
        )
        for field in _FIELDS:
            setattr(config, field, getattr(data, field))
        if data.password is not None:
            config.encrypted_password = encrypt_secret(data.password.get_secret_value())
        if connection_changed or data.password is not None:
            # A previous successful test no longer proves the new settings work.
            config.last_tested_at = None
            config.last_test_success = None
        self.db.commit()
        return config


def build_credentials(config: EmailConfiguration) -> SmtpCredentials:
    """Decrypt the company's stored password only at the moment it is needed."""
    try:
        password = decrypt_secret(config.encrypted_password)
    except DecryptionError:
        raise SmtpSendError(
            "credential_unreadable",
            "The stored SMTP password could not be read. Please re-enter it in Email Configuration.",
        )
    return SmtpCredentials(
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.username,
        password=password,
        security_type=config.security_type,
    )


def build_test_message(config: EmailConfiguration, recipient: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Email Agent: SMTP configuration test"
    message["From"] = formataddr((config.sender_name, config.email))
    message["To"] = recipient
    if config.reply_to:
        message["Reply-To"] = config.reply_to
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=config.email.split("@")[-1])
    message.set_content(
        "This is a test email from Email Agent.\n\n"
        f"Your SMTP configuration for {config.email} is working correctly."
    )
    return message


class SmtpTestService:
    def __init__(self, db: Session):
        self.db = db

    def run(self, company: Company, recipient: str) -> SmtpTestResponse:
        config = EmailConfigService(self.db).get(company)
        now = datetime.now(timezone.utc)
        try:
            smtp_client.send_message(build_credentials(config), build_test_message(config, recipient))
            result = SmtpTestResponse(
                success=True, message=f"Test email sent to {recipient}.", tested_at=now
            )
        except SmtpSendError as error:
            result = SmtpTestResponse(success=False, message=error.message, error_code=error.code, tested_at=now)

        config.last_tested_at = now
        config.last_test_success = result.success
        self.db.commit()
        return result
