from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.errors import ErrorResponse
from app.schemas.user import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.auth_service import AuthService, to_user_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={409: {"model": ErrorResponse, "description": "Email already registered"}},
)
def register(data: UserRegister, db: DbSession):
    return AuthService(db).register(data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and receive a JWT access token",
    responses={401: {"model": ErrorResponse, "description": "Invalid email or password"}},
)
def login(data: UserLogin, db: DbSession):
    return AuthService(db).login(data)


@router.get("/me", response_model=UserResponse, summary="Get the authenticated user")
def me(current_user: CurrentUser):
    return to_user_response(current_user)
