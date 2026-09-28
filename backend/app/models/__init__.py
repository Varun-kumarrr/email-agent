"""Importing this package registers every model on Base.metadata (used by Alembic)."""

from app.models.company import Company, CompanyService, SocialLink, TargetCustomer, ValueProposition
from app.models.email import EmailAccount, EmailHistory, EmailPreferences, EmailSignature
from app.models.enums import AccountType, EmailFormat, EmailProvider, EmailStatus, SecurityType
from app.models.template import EmailTemplate
from app.models.user import User

__all__ = [
    "AccountType",
    "Company",
    "CompanyService",
    "EmailAccount",
    "EmailFormat",
    "EmailHistory",
    "EmailPreferences",
    "EmailProvider",
    "EmailSignature",
    "EmailStatus",
    "EmailTemplate",
    "SecurityType",
    "SocialLink",
    "TargetCustomer",
    "User",
    "ValueProposition",
]
