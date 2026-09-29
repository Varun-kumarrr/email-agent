"""Groq provider (OpenAI-compatible Chat Completions API).

Calls the public REST endpoint directly with httpx, like the Gemini provider, so
no extra SDK is needed. The API key is sent only in the `Authorization` header
and is never logged, returned or stored.
"""

import json
import logging

import httpx

from app.services.llm.base import GeneratedEmail, LLMError, LLMProvider, LLMRequest

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ValueError("Groq API key is required")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self._transport = transport  # injectable for tests

    def __repr__(self) -> str:
        return f"GroqProvider(model={self.model!r})"

    def generate_email(self, request: LLMRequest) -> GeneratedEmail:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            # The system prompt asks for {"subject": ..., "body": ...}; JSON mode enforces valid JSON.
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException:
            raise LLMError("The AI provider timed out. Please try again.", code="llm_timeout")
        except httpx.HTTPError:
            raise LLMError("Could not reach the AI provider.", code="llm_unreachable")

        if response.status_code == 429:
            raise LLMError("AI provider rate limit or quota reached. Try again later.", code="llm_rate_limited")
        if response.status_code in (401, 403):
            raise LLMError("The AI provider rejected the API key. Check GROQ_API_KEY.", code="llm_auth_failed")
        if response.status_code >= 400:
            logger.warning("Groq request failed status=%s", response.status_code)
            raise LLMError("The AI provider returned an error.", code="llm_error")

        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> GeneratedEmail:
        try:
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            subject, body = str(result["subject"]).strip(), str(result["body"]).strip()
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMError("The AI provider returned an unexpected response.", code="llm_bad_response")
        if not subject or not body:
            raise LLMError("The AI provider returned an empty email.", code="llm_bad_response")
        return GeneratedEmail(subject=subject, body=body)
