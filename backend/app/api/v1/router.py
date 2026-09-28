from fastapi import APIRouter

from app.api.v1.endpoints import auth, company, email_config, signature

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(company.router)
api_router.include_router(email_config.router)
api_router.include_router(signature.router)
