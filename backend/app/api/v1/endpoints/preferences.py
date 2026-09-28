from fastapi import APIRouter

from app.core.dependencies import CurrentCompany, DbSession
from app.schemas.preferences import PreferencesResponse, PreferencesUpdate
from app.services.preferences_service import PreferencesService

router = APIRouter(prefix="/preferences", tags=["Email Preferences"])


@router.get(
    "",
    response_model=PreferencesResponse,
    summary="Get email sending preferences",
    description="Returns defaults until preferences are saved.",
)
def get_preferences(company: CurrentCompany, db: DbSession):
    service = PreferencesService(db)
    return service.to_response(company, service.get(company))


@router.put("", response_model=PreferencesResponse, summary="Save email sending preferences")
def update_preferences(data: PreferencesUpdate, company: CurrentCompany, db: DbSession):
    service = PreferencesService(db)
    return service.to_response(company, service.update(company, data))
