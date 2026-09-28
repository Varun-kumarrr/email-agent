from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.exceptions import AppError

app = FastAPI(title="Email Agent API", version="1.0.0")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        headers=exc.headers,
    )


app.include_router(api_router)


@app.get("/", tags=["Health"])
def read_root():
    return {"message": "Email Agent API is running"}
