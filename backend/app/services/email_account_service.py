"""Email accounts: CRUD, default-account rules and account selection for sending.

Every lookup is scoped to the authenticated company, so an account ID that belongs
to another company behaves exactly like a missing one (404).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.encryption import DecryptionError, decrypt_secret, encrypt_secret
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models import AccountType, Company, EmailAccount, EmailProvider
from app.schemas.email_account import EmailAccountCreate, EmailAccountResponse, EmailAccountUpdate
from app.services.smtp_client import SmtpCredentials, SmtpSendError

_SMTP_CONNECTION_FIELDS = ("smtp_host", "smtp_port", "smtp_username", "security_type", "email_address")


def infer_provider(smtp_host: str) -> EmailProvider:
    host = smtp_host.lower()
    if host.endswith("gmail.com") or host.endswith("googlemail.com"):
        return EmailProvider.GMAIL
    if host.endswith("office365.com") or host.endswith("outlook.com"):
        return EmailProvider.OUTLOOK
    return EmailProvider.GENERIC


def to_response(account: EmailAccount) -> EmailAccountResponse:
    return EmailAccountResponse(
        id=account.id,
        account_name=account.account_name,
        provider=account.provider,
        account_type=account.account_type,
        email_address=account.email_address,
        sender_name=account.sender_name,
        reply_to=account.reply_to,
        smtp_host=account.smtp_host,
        smtp_port=account.smtp_port,
        smtp_username=account.smtp_username,
        security_type=account.security_type,
        password_configured=bool(account.encrypted_smtp_password),
        oauth_connected=bool(account.encrypted_oauth_refresh_token or account.encrypted_oauth_access_token),
        oauth_token_expires_at=account.oauth_token_expires_at,
        is_active=account.is_active,
        is_default=account.is_default,
        last_tested_at=account.last_tested_at,
        last_test_success=account.last_test_success,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def build_smtp_credentials(account: EmailAccount) -> SmtpCredentials:
    """Decrypt the stored SMTP password only at the moment it is needed."""
    if account.account_type != AccountType.SMTP:
        raise SmtpSendError("wrong_account_type", "This account does not use SMTP.")
    try:
        password = decrypt_secret(account.encrypted_smtp_password or "")
    except DecryptionError:
        raise SmtpSendError(
            "credential_unreadable",
            "The stored SMTP password could not be read. Please re-enter it for this email account.",
        )
    return SmtpCredentials(
        host=account.smtp_host,
        port=account.smtp_port,
        username=account.smtp_username,
        password=password,
        security_type=account.security_type,
    )


class EmailAccountService:
    def __init__(self, db: Session):
        self.db = db

    # ----- queries -----------------------------------------------------------------

    def list(self, company: Company) -> list[EmailAccount]:
        return list(
            self.db.scalars(
                select(EmailAccount)
                .where(EmailAccount.company_id == company.id)
                .order_by(EmailAccount.is_default.desc(), EmailAccount.created_at, EmailAccount.id)
            )
        )

    def find(self, company: Company, account_id: uuid.UUID) -> EmailAccount | None:
        return self.db.scalar(
            select(EmailAccount).where(EmailAccount.id == account_id, EmailAccount.company_id == company.id)
        )

    def get(self, company: Company, account_id: uuid.UUID) -> EmailAccount:
        account = self.find(company, account_id)
        if account is None:
            raise NotFoundError("Email account not found")
        return account

    def default_account(self, company: Company) -> EmailAccount | None:
        return self.db.scalar(
            select(EmailAccount).where(
                EmailAccount.company_id == company.id,
                EmailAccount.is_default.is_(True),
                EmailAccount.is_active.is_(True),
            )
        )

    def primary_smtp(self, company: Company) -> EmailAccount | None:
        """The SMTP account the legacy single-configuration API (/email-config) works on:
        the default account if it is SMTP, otherwise the oldest SMTP account."""
        accounts = [a for a in self.list(company) if a.account_type == AccountType.SMTP]
        return accounts[0] if accounts else None

    def resolve_for_sending(self, company: Company, account_id: uuid.UUID | None) -> EmailAccount:
        """The account an email will be sent from: the one requested, or the company default."""
        if account_id is not None:
            account = self.get(company, account_id)
            if not account.is_active:
                raise BadRequestError("This email account is inactive. Activate it or choose another account.")
            return account
        account = self.default_account(company)
        if account is None:
            raise NotFoundError("Configure an email account (SMTP or OAuth) before sending emails.")
        return account

    # ----- commands ----------------------------------------------------------------

    def create_smtp(self, company: Company, data: EmailAccountCreate) -> EmailAccount:
        if data.is_default and not data.is_active:
            raise BadRequestError("An inactive account cannot be the default account.")
        self._ensure_unique(company, AccountType.SMTP, str(data.email_address))

        account = EmailAccount(
            company_id=company.id,
            account_name=data.account_name,
            provider=data.provider,
            account_type=AccountType.SMTP,
            email_address=str(data.email_address).lower(),
            sender_name=data.sender_name,
            reply_to=data.reply_to,
            smtp_host=data.smtp_host,
            smtp_port=data.smtp_port,
            smtp_username=data.smtp_username,
            encrypted_smtp_password=encrypt_secret(data.password.get_secret_value()),
            security_type=data.security_type,
            is_active=data.is_active,
            is_default=False,
        )
        make_default = data.is_default or (data.is_active and self.default_account(company) is None)
        return self._save_new(company, account, make_default)

    def save_oauth_account(self, company: Company, account: EmailAccount) -> EmailAccount:
        """Persist a new OAuth account built by the OAuth flow (becomes default if none exists)."""
        return self._save_new(company, account, make_default=self.default_account(company) is None)

    def update(self, company: Company, account_id: uuid.UUID, data: EmailAccountUpdate) -> EmailAccount:
        account = self.get(company, account_id)
        changes = data.model_dump(exclude_unset=True)
        password = changes.pop("password", None)

        smtp_only = {"smtp_host", "smtp_port", "smtp_username", "security_type"} & changes.keys()
        if account.account_type == AccountType.OAUTH and (smtp_only or password is not None or "email_address" in changes):
            raise BadRequestError("SMTP settings and the address of an OAuth account cannot be edited; reconnect it instead.")
        for required in ("account_name", "sender_name", "smtp_host", "smtp_port", "smtp_username", "security_type", "email_address", "is_active"):
            if required in changes and changes[required] is None:
                raise BadRequestError(f"{required} cannot be null")

        if "email_address" in changes:
            changes["email_address"] = str(changes["email_address"]).lower()
            if changes["email_address"] != account.email_address:
                self._ensure_unique(company, account.account_type, changes["email_address"])

        connection_changed = any(f in changes and changes[f] != getattr(account, f) for f in _SMTP_CONNECTION_FIELDS)
        deactivating = changes.get("is_active") is False and account.is_active

        for field, value in changes.items():
            setattr(account, field, value)
        if password is not None:
            account.encrypted_smtp_password = encrypt_secret(password.get_secret_value())
        if connection_changed or password is not None:
            # A previous successful test no longer proves the new settings work.
            account.last_tested_at = None
            account.last_test_success = None

        if deactivating and account.is_default:
            account.is_default = False
            self.db.flush()
            self._promote_default(company, exclude=account.id)
        elif changes.get("is_active") and self.default_account(company) is None:
            self.db.flush()
            account.is_default = True

        self._commit_or_conflict()
        return account

    def delete(self, company: Company, account_id: uuid.UUID) -> None:
        account = self.get(company, account_id)
        was_default = account.is_default
        self.db.delete(account)
        self.db.flush()
        if was_default:
            self._promote_default(company, exclude=account_id)
        self.db.commit()

    def set_default(self, company: Company, account_id: uuid.UUID) -> EmailAccount:
        account = self.get(company, account_id)
        if not account.is_active:
            raise BadRequestError("Activate the account before making it the default.")
        if not account.is_default:
            self._clear_default(company)
            account.is_default = True
            self.db.commit()
        return account

    # ----- helpers -----------------------------------------------------------------

    def _ensure_unique(self, company: Company, account_type: AccountType, email_address: str) -> None:
        exists = self.db.scalar(
            select(EmailAccount.id).where(
                EmailAccount.company_id == company.id,
                EmailAccount.account_type == account_type,
                EmailAccount.email_address == email_address.lower(),
            )
        )
        if exists:
            raise ConflictError(f"An {account_type.value} account for {email_address} already exists.")

    def _clear_default(self, company: Company) -> None:
        for other in self.db.scalars(
            select(EmailAccount).where(EmailAccount.company_id == company.id, EmailAccount.is_default.is_(True))
        ):
            other.is_default = False
        self.db.flush()  # release the one-default index before setting a new default

    def _promote_default(self, company: Company, exclude: uuid.UUID) -> None:
        candidate = self.db.scalar(
            select(EmailAccount)
            .where(
                EmailAccount.company_id == company.id,
                EmailAccount.is_active.is_(True),
                EmailAccount.id != exclude,
            )
            .order_by(EmailAccount.created_at, EmailAccount.id)
            .limit(1)
        )
        if candidate is not None:
            candidate.is_default = True

    def _save_new(self, company: Company, account: EmailAccount, make_default: bool) -> EmailAccount:
        if make_default:
            self._clear_default(company)
            account.is_default = True
        self.db.add(account)
        self._commit_or_conflict()
        return account

    def _commit_or_conflict(self) -> None:
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ConflictError("This email account conflicts with an existing account.")
