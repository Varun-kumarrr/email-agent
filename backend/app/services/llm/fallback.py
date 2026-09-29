"""Ordered chain of real LLM providers (e.g. Groq, then Gemini).

Each provider is tried in turn; the first successful email is returned, tagged
with the provider that wrote it. If every provider fails, one LLMError is raised
and the email agent applies its existing mock fallback (LLM_FALLBACK_TO_MOCK).
Failures are logged with the provider name and safe error code only.
"""

import logging

from app.services.llm.base import GeneratedEmail, LLMError, LLMProvider, LLMRequest

logger = logging.getLogger(__name__)


class FallbackLLMProvider(LLMProvider):
    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("At least one provider is required")
        self.providers = providers
        self.name = providers[0].name  # reported when the chain itself is referenced

    def __repr__(self) -> str:
        return f"FallbackLLMProvider({', '.join(repr(p) for p in self.providers)})"

    def generate_email(self, request: LLMRequest) -> GeneratedEmail:
        failed: list[str] = []
        last_error: LLMError | None = None
        for provider in self.providers:
            try:
                email = provider.generate_email(request)
            except LLMError as error:
                logger.warning("LLM provider %s failed code=%s; trying the next provider", provider.name, error.code)
                failed.append(provider.name)
                last_error = error
                continue
            email.provider = provider.name
            if failed:
                email.warning = (
                    f"The primary AI provider ({', '.join(failed)}) was unavailable; "
                    f"this draft was written by {provider.name}."
                )
            return email
        raise LLMError(
            f"The AI providers ({', '.join(failed)}) are unavailable right now.",
            code=last_error.code if last_error else "llm_error",
        )
