from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging

configure_logging(settings.LOG_LEVEL)

app = FastAPI(title="Email Agent API", version="1.0.0")

register_exception_handlers(app)
app.include_router(api_router)


@app.get("/", tags=["Health"])
def read_root():
    return {"message": "Email Agent API is running"}
