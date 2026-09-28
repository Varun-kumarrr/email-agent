from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.encryption import encrypt_secret
from app.core.exceptions import ConflictError, NotFoundError
from app.models import Company, EmailConfiguration
from app.schemas.email_config import EmailConfigCreate, EmailConfigResponse, EmailConfigUpdate

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
