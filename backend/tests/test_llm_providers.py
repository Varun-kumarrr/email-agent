import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.llm import GeminiProvider, LLMError, LLMRequest, MockLLMProvider, get_llm_provider

API_KEY = "fake-gemini-key-for-tests"

CONTEXT = {
    "company": {
        "name": "ABC Technologies",
        "description": "AI-powered CRM solutions for small and medium-sized businesses.",
        "services": [{"name": "CRM"}, {"name": "Sales automation"}, {"name": "Analytics"}],
        "target_customers": [{"segment": "Small and medium-sized businesses"}],
        "value_propositions": [{"statement": "Reduce manual sales work and improve productivity."}],
    },
    "recipient_name": "Priya",
    "purpose": "Introduce our CRM to a small business owner",
    "sender_name": "Anjali",
}


def _settings(**overrides):
    return Settings(_env_file=None, **overrides)


def test_factory_uses_mock_when_configured():
    assert isinstance(get_llm_provider(_settings(LLM_PROVIDER="mock", LLM_API_KEY=SecretStr(API_KEY))), MockLLMProvider)


def test_factory_falls_back_to_mock_without_api_key():
    assert isinstance(get_llm_provider(_settings(LLM_PROVIDER="gemini", LLM_API_KEY=SecretStr(""))), MockLLMProvider)


def test_factory_uses_gemini_with_api_key():
    provider = get_llm_provider(_settings(LLM_PROVIDER="gemini", LLM_API_KEY=SecretStr(API_KEY)))
    assert isinstance(provider, GeminiProvider)
    assert API_KEY not in repr(provider)


def test_mock_provider_uses_only_company_context():
    email = MockLLMProvider().generate_email(LLMRequest("sys", "user", context=CONTEXT))
    assert "ABC Technologies" in email.subject
    assert "Hi Priya," in email.body
    assert "CRM, Sales automation and Analytics" in email.body
    assert "reduce manual sales work" in email.body.lower()
    assert "Best regards,\nAnjali" in email.body


def _gemini(handler):
    return GeminiProvider(API_KEY, "gemini-2.5-flash", transport=httpx.MockTransport(handler))


def test_gemini_success_parses_json_and_sends_key_in_header():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["payload"] = json.loads(request.content)
        text = json.dumps({"subject": "Hello", "body": "Hi Priya,\n\nBody"})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    email = _gemini(handler).generate_email(LLMRequest("SYSTEM RULES", "USER TASK"))
    assert (email.subject, email.body) == ("Hello", "Hi Priya,\n\nBody")
    assert seen["key"] == API_KEY
    assert API_KEY not in seen["url"]
    assert seen["payload"]["system_instruction"]["parts"][0]["text"] == "SYSTEM RULES"
    assert seen["payload"]["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.parametrize(
    ("status", "code"),
    [(429, "llm_rate_limited"), (403, "llm_auth_failed"), (500, "llm_error")],
)
def test_gemini_http_errors(status, code):
    with pytest.raises(LLMError) as info:
        _gemini(lambda r: httpx.Response(status, json={"error": {"message": f"key {API_KEY} bad"}})).generate_email(
            LLMRequest("s", "u")
        )
    assert info.value.code == code
    assert API_KEY not in info.value.message


def test_gemini_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(LLMError) as info:
        _gemini(handler).generate_email(LLMRequest("s", "u"))
    assert info.value.code == "llm_timeout"


def test_gemini_malformed_response():
    handler = lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]})
    with pytest.raises(LLMError) as info:
        _gemini(handler).generate_email(LLMRequest("s", "u"))
    assert info.value.code == "llm_bad_response"
