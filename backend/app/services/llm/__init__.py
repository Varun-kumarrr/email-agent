"""LLM providers and the factory that picks one from settings."""

import logging

from app.core.config import Settings, settings as app_settings
from app.services.llm.base import GeneratedEmail, LLMError, LLMProvider, LLMRequest
from app.services.llm.fallback import FallbackLLMProvider
from app.services.llm.gemini import GeminiProvider
from app.services.llm.groq import GroqProvider
from app.services.llm.mock import MockLLMProvider

logger = logging.getLogger(__name__)

__all__ = [
    "FallbackLLMProvider",
    "GeneratedEmail",
    "GeminiProvider",
    "GroqProvider",
    "LLMError",
    "LLMProvider",
    "LLMRequest",
    "MockLLMProvider",
    "get_llm_provider",
]


def _gemini(settings: Settings) -> GeminiProvider | None:
    api_key = settings.LLM_API_KEY.get_secret_value().strip()
    if not api_key:
        return None
    return GeminiProvider(api_key=api_key, model=settings.LLM_MODEL, timeout=settings.LLM_TIMEOUT_SECONDS)


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Pick the provider(s) from settings.

    groq   -> Groq, then Gemini if Groq fails (each only if its key is set)
    gemini -> Gemini
    mock   -> the offline mock provider

    A provider without an API key is skipped; with no usable provider the mock is
    used. The email agent adds the final mock fallback when every provider fails.
    """
    settings = settings or app_settings
    provider = settings.LLM_PROVIDER.strip().lower()

    if provider == "mock":
        return MockLLMProvider()
    if provider == "gemini":
        gemini = _gemini(settings)
        if gemini is None:
            logger.info("LLM_API_KEY not set; using the mock LLM provider")
            return MockLLMProvider()
        return gemini
    if provider == "groq":
        chain: list[LLMProvider] = []
        groq_key = settings.GROQ_API_KEY.get_secret_value().strip()
        if groq_key:
            chain.append(GroqProvider(api_key=groq_key, model=settings.GROQ_MODEL, timeout=settings.LLM_TIMEOUT_SECONDS))
        else:
            logger.info("GROQ_API_KEY not set; skipping the Groq provider")
        gemini = _gemini(settings)
        if gemini is not None:
            chain.append(gemini)
        if not chain:
            logger.info("No LLM API key set; using the mock LLM provider")
            return MockLLMProvider()
        return chain[0] if len(chain) == 1 else FallbackLLMProvider(chain)

    logger.warning("Unknown LLM_PROVIDER %r; using the mock LLM provider", provider)
    return MockLLMProvider()
