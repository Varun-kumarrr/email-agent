"""Legacy single-configuration API (/api/v1/email-config), kept for backward compatibility.

It now works on the company's *primary SMTP account* (see EmailAccountService.primary_smtp):
POST creates the first SMTP account (409 if one exists), GET/PUT read and update it, and
/test sends a test email through it. New clients should use /api/v1/email-accounts.
"""

from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import AccountType, Company, EmailAccount, EmailFormat, EmailHistory, EmailStatus, User
from app.schemas.email_account import EmailAccountCreate, EmailAccountUpdate
from app.schemas.email_config import EmailConfigCreate, EmailConfigResponse, EmailConfigUpdate, SmtpTestResponse
from app.services import smtp_client
from app.services.email_account_service import (
    EmailAccountService,
    build_smtp_credentials,
    infer_provider,
    with_provider_hint,
)
from app.services.gmail_delivery import is_gmail_oauth, send_via_gmail
from app.services.smtp_client import SmtpSendError

# Kept so existing imports keep working.
build_credentials = build_smtp_credentials


def to_response(account: EmailAccount) -> EmailConfigResponse:
    return EmailConfigResponse(
        email=account.email_address,
        smtp_host=account.smtp_host,
        smtp_port=account.smtp_port,
        username=account.smtp_username,
        security_type=account.security_type,
        sender_name=account.sender_name,
        reply_to=account.reply_to,
        password_configured=bool(account.encrypted_smtp_password),
        last_tested_at=account.last_tested_at,
        last_test_success=account.last_test_success,
        updated_at=account.updated_at,
    )


class EmailConfigService:
    def __init__(self, db: Session):
        self.db = db
        self.accounts = EmailAccountService(db)

    def find(self, company: Company) -> EmailAccount | None:
        return self.accounts.primary_smtp(company)

    def get(self, company: Company) -> EmailAccount:
        account = self.find(company)
        if account is None:
            raise NotFoundError("Email configuration not found. Configure your SMTP account first.")
        return account

    def create(self, company: Company, data: EmailConfigCreate) -> EmailAccount:
        if self.find(company) is not None:
            raise ConflictError("Email configuration already exists. Use PUT to update it.")
        return self.accounts.create_smtp(
            company,
            EmailAccountCreate(
                account_name="Primary SMTP",
                provider=infer_provider(data.smtp_host),
                email_address=data.email,
                sender_name=data.sender_name,
                reply_to=data.reply_to,
                smtp_host=data.smtp_host,
                smtp_port=data.smtp_port,
                smtp_username=data.username,
                password=data.password,
                security_type=data.security_type,
            ),
        )

    def update(self, company: Company, data: EmailConfigUpdate) -> EmailAccount:
        account = self.get(company)
        changes = {
            "email_address": data.email,
            "smtp_host": data.smtp_host,
            "smtp_port": data.smtp_port,
            "smtp_username": data.username,
            "security_type": data.security_type,
            "sender_name": data.sender_name,
            "reply_to": data.reply_to,  # PUT semantics: null clears it
        }
        if data.password is not None:
            changes["password"] = data.password
        return self.accounts.update(company, account.id, EmailAccountUpdate(**changes))


def build_test_message(account: EmailAccount, recipient: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Email Agent: email account test"
    message["From"] = formataddr((account.sender_name, account.email_address))
    message["To"] = recipient
    if account.reply_to:
        message["Reply-To"] = account.reply_to
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=account.email_address.split("@")[-1])
    message.set_content(
        "This is a test email from Email Agent.\n\n"
        f"The email account {account.email_address} is working correctly."
    )
    return message


def run_account_test(db: Session, account: EmailAccount, recipient: str, user: User | None = None) -> SmtpTestResponse:
    """Send a test email through `account`, record the result on the account ("Last test")
    and in the email history as a test email (is_test=True)."""
    now = datetime.now(timezone.utc)
    message = build_test_message(account, recipient)
    error: SmtpSendError | None = None
    try:
        if account.account_type == AccountType.SMTP:
            smtp_client.send_message(build_smtp_credentials(account), message)
        elif is_gmail_oauth(account):
            send_via_gmail(db, account, message, [])
        else:
            raise SmtpSendError("not_supported", "Testing this account type is not supported yet.")
        result = SmtpTestResponse(success=True, message=f"Test email sent to {recipient}.", tested_at=now)
    except SmtpSendError as exc:
        error = with_provider_hint(exc, account.provider)
        result = SmtpTestResponse(success=False, message=error.message, error_code=error.code, tested_at=now)

    account.last_tested_at = now
    account.last_test_success = result.success
    db.add(
        EmailHistory(
            company_id=account.company_id,
            sent_by_user_id=user.id if user else None,
            email_account_id=account.id,
            sender_email=account.email_address,
            sender_name=account.sender_name,
            reply_to=account.reply_to,
            recipient=recipient.lower(),
            cc=[],
            bcc=[],
            subject=message["Subject"],
            body=message.get_content().strip(),
            email_format=EmailFormat.PLAIN_TEXT,
            status=EmailStatus.SENT if result.success else EmailStatus.FAILED,
            error_code=error.code if error else None,
            error_message=error.message if error else None,  # safe, pre-classified message only
            attempts=1,
            last_attempt_at=now,
            sent_at=now if result.success else None,
            is_test=True,
        )
    )
    db.commit()
    return result


class SmtpTestService:
    def __init__(self, db: Session):
        self.db = db

    def run(self, company: Company, recipient: str, user: User | None = None) -> SmtpTestResponse:
        return run_account_test(self.db, EmailConfigService(self.db).get(company), recipient, user)
