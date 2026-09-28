from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import TokenResponse, UserLogin, UserRegister, UserResponse

# Used to keep login timing similar whether or not the email exists.
_DUMMY_HASH = hash_password("timing-equalizer-0")


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        has_company=user.company is not None,
        created_at=user.created_at,
    )


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)

    def register(self, data: UserRegister) -> UserResponse:
        if self.users.get_by_email(data.email):
            raise ConflictError("An account with this email already exists")
        try:
            user = self.users.create(
                email=data.email, name=data.name, hashed_password=hash_password(data.password)
            )
            self.db.commit()
        except IntegrityError:  # race between the check above and the insert
            self.db.rollback()
            raise ConflictError("An account with this email already exists")
        return to_user_response(user)

    def login(self, data: UserLogin) -> TokenResponse:
        user = self.users.get_by_email(data.email)
        if user is None:
            verify_password(data.password, _DUMMY_HASH)
            raise UnauthorizedError("Invalid email or password")
        if not verify_password(data.password, user.hashed_password) or not user.is_active:
            # Same message for unknown email and wrong password: no account enumeration.
            raise UnauthorizedError("Invalid email or password")

        return TokenResponse(
            access_token=create_access_token(user.id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=to_user_response(user),
        )
