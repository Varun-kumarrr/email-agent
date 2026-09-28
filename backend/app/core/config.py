"""Application settings loaded from environment variables (and an optional .env file).

Secrets (database password, JWT secret, LLM API key, encryption key) are only
ever read from the environment. They are never hard-coded and never returned
by any API endpoint.
"""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Email Agent API"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres@localhost:5432/email_agent"
    SQL_ECHO: bool = False

    # Authentication
    SECRET_KEY: SecretStr = Field(default=SecretStr("change-me-in-your-local-env-file"))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Symmetric key (Fernet) used to encrypt stored SMTP passwords.
    # If empty, a key is derived from SECRET_KEY (acceptable for local development only).
    ENCRYPTION_KEY: SecretStr = Field(default=SecretStr(""))

    # LLM
    LLM_PROVIDER: str = "gemini"  # "gemini" or "mock"
    LLM_API_KEY: SecretStr = Field(default=SecretStr(""))
    LLM_MODEL: str = "gemini-2.5-flash"
    LLM_TIMEOUT_SECONDS: float = 30.0
    # If the real provider fails (quota, network), fall back to the mock provider
    # and flag the response, instead of failing the request.
    LLM_FALLBACK_TO_MOCK: bool = True

    # SMTP
    SMTP_TIMEOUT_SECONDS: float = 15.0
    SMTP_RETRY_BACKOFF_SECONDS: float = 1.0

    # CORS — comma separated list of allowed frontend origins
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
