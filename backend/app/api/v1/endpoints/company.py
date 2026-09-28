from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate
from app.services.company_service import CompanyProfileService

router = APIRouter(prefix="/company", tags=["Company Profile"])


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the company profile for the authenticated user",
    responses={409: {"description": "A company profile already exists"}},
)
def create_company(data: CompanyCreate, current_user: CurrentUser, db: DbSession):
    return CompanyProfileService(db).create(current_user, data)


@router.get(
    "",
    response_model=CompanyResponse,
    summary="Get the authenticated user's company profile",
    responses={404: {"description": "No company profile yet"}},
)
def get_company(current_user: CurrentUser, db: DbSession):
    return CompanyProfileService(db).get_for_user(current_user)


@router.put(
    "",
    response_model=CompanyResponse,
    summary="Replace the authenticated user's company profile",
    responses={404: {"description": "No company profile yet"}},
)
def update_company(data: CompanyUpdate, current_user: CurrentUser, db: DbSession):
    return CompanyProfileService(db).update(current_user, data)
