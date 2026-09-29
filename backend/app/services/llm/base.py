"""LLM provider abstraction.

The email agent depends only on `LLMProvider`, so providers (Gemini, OpenAI,
a local model, a mock) can be swapped without touching business logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    # Structured copy of the same context. Real providers ignore it; the mock
    # provider uses it to build a realistic email without calling a model.
    context: dict[str, Any] = field(default_factory=dict)
    temperature: float = 0.7


@dataclass
class GeneratedEmail:
    subject: str
    body: str
    # Set by FallbackLLMProvider: which provider actually wrote the email, and a
    # user-facing note when it was not the primary provider.
    provider: str | None = None
    warning: str | None = None


class LLMError(Exception):
    """Provider failure with a message that is safe to show users."""

    def __init__(self, message: str, *, code: str = "llm_error"):
        self.message = message
        self.code = code
        super().__init__(message)


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate_email(self, request: LLMRequest) -> GeneratedEmail:
        """Return a subject and plain-text body, or raise LLMError."""
