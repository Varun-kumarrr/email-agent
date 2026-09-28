"""Importing this package registers every model on Base.metadata (used by Alembic)."""

from app.models.company import Company, CompanyService, SocialLink, TargetCustomer, ValueProposition
from app.models.email import EmailConfiguration, EmailHistory, EmailPreferences, EmailSignature
from app.models.enums import EmailFormat, EmailStatus, SecurityType
from app.models.user import User

__all__ = [
    "Company",
    "CompanyService",
    "EmailConfiguration",
    "EmailFormat",
    "EmailHistory",
    "EmailPreferences",
    "EmailSignature",
    "EmailStatus",
    "SecurityType",
    "SocialLink",
    "TargetCustomer",
    "User",
    "ValueProposition",
]
