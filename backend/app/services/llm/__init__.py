"""LLM providers and the factory that picks one from settings."""

import logging

from app.core.config import Settings, settings as app_settings
from app.services.llm.base import GeneratedEmail, LLMError, LLMProvider, LLMRequest
from app.services.llm.gemini import GeminiProvider
from app.services.llm.mock import MockLLMProvider

logger = logging.getLogger(__name__)

__all__ = [
    "GeneratedEmail",
    "GeminiProvider",
    "LLMError",
    "LLMProvider",
    "LLMRequest",
    "MockLLMProvider",
    "get_llm_provider",
]


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Gemini when configured with an API key, otherwise the offline mock provider."""
    settings = settings or app_settings
    provider = settings.LLM_PROVIDER.strip().lower()
    api_key = settings.LLM_API_KEY.get_secret_value().strip()

    if provider == "mock":
        return MockLLMProvider()
    if provider == "gemini":
        if not api_key:
            logger.info("LLM_API_KEY not set; using the mock LLM provider")
            return MockLLMProvider()
        return GeminiProvider(api_key=api_key, model=settings.LLM_MODEL, timeout=settings.LLM_TIMEOUT_SECONDS)

    logger.warning("Unknown LLM_PROVIDER %r; using the mock LLM provider", provider)
    return MockLLMProvider()
