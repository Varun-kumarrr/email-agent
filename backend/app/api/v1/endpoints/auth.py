from fastapi import APIRouter, Request, status

from app.core.dependencies import CurrentUser, DbSession
from app.core.exceptions import UnauthorizedError
from app.core.rate_limit import client_ip, login_limiter, register_limiter
from app.schemas.errors import ErrorResponse
from app.schemas.user import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.auth_service import AuthService, to_user_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={
        409: {"model": ErrorResponse, "description": "Email already registered"},
        429: {"model": ErrorResponse, "description": "Too many registrations"},
    },
)
def register(data: UserRegister, request: Request, db: DbSession):
    register_limiter.hit(client_ip(request))
    return AuthService(db).register(data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and receive a JWT access token",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid email or password"},
        429: {"model": ErrorResponse, "description": "Too many login attempts"},
    },
)
def login(data: UserLogin, request: Request, db: DbSession):
    # Limit failed attempts per IP + account so one attacker can't lock out every user.
    # Only failures count; once the limit is reached even a correct password gets 429.
    key = f"{client_ip(request)}:{data.email.lower()}"
    login_limiter.check(key)
    try:
        return AuthService(db).login(data)
    except UnauthorizedError:
        login_limiter.record(key)
        raise


@router.get("/me", response_model=UserResponse, summary="Get the authenticated user")
def me(current_user: CurrentUser):
    return to_user_response(current_user)
