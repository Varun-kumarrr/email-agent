"""Google Gemini provider (free tier via Google AI Studio API keys).

Calls the public REST endpoint directly with httpx, so no extra SDK is needed.
The API key is sent in the `x-goog-api-key` header (never in the URL) and is
never logged.
"""

import json
import logging

import httpx

from app.services.llm.base import GeneratedEmail, LLMError, LLMProvider, LLMRequest

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {"subject": {"type": "STRING"}, "body": {"type": "STRING"}},
    "required": ["subject", "body"],
}


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ValueError("Gemini API key is required")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self._transport = transport  # injectable for tests

    def __repr__(self) -> str:
        return f"GeminiProvider(model={self.model!r})"

    def generate_email(self, request: LLMRequest) -> GeneratedEmail:
        payload = {
            "system_instruction": {"parts": [{"text": request.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": request.user_prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
            },
        }
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    GEMINI_URL.format(model=self.model),
                    headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException:
            raise LLMError("The AI provider timed out. Please try again.", code="llm_timeout")
        except httpx.HTTPError:
            raise LLMError("Could not reach the AI provider.", code="llm_unreachable")

        if response.status_code == 429:
            raise LLMError("AI provider rate limit or free-tier quota reached. Try again later.", code="llm_rate_limited")
        if response.status_code in (401, 403):
            raise LLMError("The AI provider rejected the API key. Check LLM_API_KEY.", code="llm_auth_failed")
        if response.status_code >= 400:
            logger.warning("Gemini request failed status=%s", response.status_code)
            raise LLMError("The AI provider returned an error.", code="llm_error")

        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> GeneratedEmail:
        try:
            data = response.json()
            candidate = data["candidates"][0]
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
            result = json.loads(text)
            subject, body = str(result["subject"]).strip(), str(result["body"]).strip()
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMError("The AI provider returned an unexpected response.", code="llm_bad_response")
        if not subject or not body:
            raise LLMError("The AI provider returned an empty email.", code="llm_bad_response")
        return GeneratedEmail(subject=subject, body=body)
