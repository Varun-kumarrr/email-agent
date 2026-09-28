from fastapi import APIRouter

from app.api.v1.endpoints import agent, auth, company, email_config, emails, preferences, signature
from app.schemas.errors import COMMON_ERROR_RESPONSES

api_router = APIRouter(prefix="/api/v1", responses=COMMON_ERROR_RESPONSES)
api_router.include_router(auth.router)
api_router.include_router(company.router)
api_router.include_router(email_config.router)
api_router.include_router(signature.router)
api_router.include_router(preferences.router)
api_router.include_router(agent.router)
api_router.include_router(emails.router)
