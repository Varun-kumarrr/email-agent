"""Password hashing and JWT helpers."""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError


def hash_password(password: str) -> str:
    # bcrypt generates a random salt per hash; the salt is stored inside the hash string.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "iat": now, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Return the user id from a valid token, or raise UnauthorizedError."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],  # pin the algorithm (prevents "alg: none" attacks)
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid authentication token")

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid authentication token")
    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        raise UnauthorizedError("Invalid authentication token")
