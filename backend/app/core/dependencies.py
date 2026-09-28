"""Reusable FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.database import get_db
from app.models import Company, User
from app.repositories.user_repository import UserRepository
from app.services.company_service import CompanyProfileService

bearer_scheme = HTTPBearer(auto_error=False, description="JWT from POST /api/v1/auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Resolve the authenticated user from `Authorization: Bearer <token>`."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Missing authentication token")

    user_id = decode_access_token(credentials.credentials)
    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid authentication token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_company(db: DbSession, current_user: CurrentUser) -> Company:
    """The authenticated user's company.

    Every company-owned resource (email config, signature, preferences, history,
    AI generation, sending) is resolved through this dependency. Resources are
    never looked up by an ID supplied by the client, so one company can never
    read or act on another company's data.
    """
    return CompanyProfileService(db).get_for_user(current_user)


CurrentCompany = Annotated[Company, Depends(get_current_company)]
