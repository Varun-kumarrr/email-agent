"""Groq as the primary LLM provider: provider, selection, fallback chain and secrecy."""

import json
import logging

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.dependencies import get_llm
from app.main import app
from app.services.llm import (
    FallbackLLMProvider,
    GeminiProvider,
    GroqProvider,
    LLMError,
    LLMRequest,
    MockLLMProvider,
    get_llm_provider,
)
from app.services.llm.groq import GROQ_URL
from tests.test_company import create_company

GROQ_KEY = "gsk_" + "FAKEGROQKEYFORTESTS0000000"
GEMINI_KEY = "AIza" + "FAKE_GEMINI_KEY_FOR_TESTS"
GENERATE = "/api/v1/agent/generate-email"
REQUEST = {"recipient_name": "Priya", "recipient_email": "priya@example.com", "purpose": "Introduce our CRM"}


def _settings(**overrides):
    return Settings(_env_file=None, **overrides)


def _groq_ok(subject="Groq subject", body="Hi Priya,\n\nWritten by Groq."):
    content = json.dumps({"subject": subject, "body": body})
    return lambda r: httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def _gemini_ok(subject="Gemini subject", body="Hi Priya,\n\nWritten by Gemini."):
    text = json.dumps({"subject": subject, "body": body})
    return lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def _failing(status):
    return lambda r: httpx.Response(status, json={"error": {"message": f"bad key {GROQ_KEY} {GEMINI_KEY}"}})


def groq(handler, model="openai/gpt-oss-120b"):
    return GroqProvider(GROQ_KEY, model, transport=httpx.MockTransport(handler))


def gemini(handler):
    return GeminiProvider(GEMINI_KEY, "gemini-3.8-flash", transport=httpx.MockTransport(handler))


# ----- provider -------------------------------------------------------------------------


def test_groq_initialization_requires_key_and_hides_it():
    with pytest.raises(ValueError):
        GroqProvider("", "openai/gpt-oss-120b")
    provider = GroqProvider(GROQ_KEY, "openai/gpt-oss-120b")
    assert provider.name == "groq" and provider.model == "openai/gpt-oss-120b"
    assert GROQ_KEY not in repr(provider)


def test_groq_success_sends_chat_completion_with_key_in_header():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return _groq_ok()(request)

    email = groq(handler, model="custom/model").generate_email(LLMRequest("SYSTEM RULES", "USER TASK", temperature=0.4))
    assert (email.subject, email.body) == ("Groq subject", "Hi Priya,\n\nWritten by Groq.")
    assert seen["url"] == GROQ_URL and GROQ_KEY not in seen["url"]
    assert seen["auth"] == f"Bearer {GROQ_KEY}"
    payload = seen["payload"]
    assert payload["model"] == "custom/model"
    assert payload["messages"] == [
        {"role": "system", "content": "SYSTEM RULES"},
        {"role": "user", "content": "USER TASK"},
    ]
    assert payload["response_format"] == {"type": "json_object"} and payload["temperature"] == 0.4


@pytest.mark.parametrize(
    ("status", "code"),
    [(429, "llm_rate_limited"), (401, "llm_auth_failed"), (403, "llm_auth_failed"), (500, "llm_error"), (503, "llm_error")],
)
def test_groq_http_errors_are_sanitized(status, code, caplog):
    with caplog.at_level(logging.DEBUG), pytest.raises(LLMError) as info:
        groq(_failing(status)).generate_email(LLMRequest("s", "u"))
    assert info.value.code == code
    assert GROQ_KEY not in info.value.message and "bad key" not in info.value.message
    assert GROQ_KEY not in caplog.text


def test_groq_timeout_and_network_errors():
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    def unreachable(request):
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(LLMError) as info:
        groq(timeout).generate_email(LLMRequest("s", "u"))
    assert info.value.code == "llm_timeout"
    with pytest.raises(LLMError) as info:
        groq(unreachable).generate_email(LLMRequest("s", "u"))
    assert info.value.code == "llm_unreachable"


@pytest.mark.parametrize(
    "response",
    [
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": [{"message": {"content": json.dumps({"subject": "only subject"})}}]},
        {"choices": [{"message": {"content": json.dumps({"subject": " ", "body": " "})}}]},
        {"choices": []},
        {},
    ],
)
def test_groq_malformed_responses(response):
    with pytest.raises(LLMError) as info:
        groq(lambda r: httpx.Response(200, json=response)).generate_email(LLMRequest("s", "u"))
    assert info.value.code == "llm_bad_response"


# ----- selection and configuration ----------------------------------------------------------


def test_groq_is_the_default_provider_with_gemini_as_fallback(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)  # the test suite sets "mock"; check the real default
    provider = get_llm_provider(_settings(GROQ_API_KEY=SecretStr(GROQ_KEY), LLM_API_KEY=SecretStr(GEMINI_KEY)))
    assert isinstance(provider, FallbackLLMProvider)
    assert [type(p) for p in provider.providers] == [GroqProvider, GeminiProvider]
    assert GROQ_KEY not in repr(provider) and GEMINI_KEY not in repr(provider)


def test_default_groq_model_and_override():
    default = get_llm_provider(_settings(LLM_PROVIDER="groq", GROQ_API_KEY=SecretStr(GROQ_KEY)))
    assert isinstance(default, GroqProvider) and default.model == "openai/gpt-oss-120b"
    custom = get_llm_provider(_settings(LLM_PROVIDER="groq", GROQ_API_KEY=SecretStr(GROQ_KEY), GROQ_MODEL="other/model"))
    assert custom.model == "other/model"


def test_groq_model_read_from_environment(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "env/model")
    monkeypatch.setenv("GROQ_API_KEY", GROQ_KEY)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    provider = get_llm_provider(Settings(_env_file=None))
    assert isinstance(provider, GroqProvider) and provider.model == "env/model"


def test_missing_groq_key_uses_gemini_then_mock():
    only_gemini = get_llm_provider(
        _settings(LLM_PROVIDER="groq", GROQ_API_KEY=SecretStr(""), LLM_API_KEY=SecretStr(GEMINI_KEY))
    )
    assert isinstance(only_gemini, GeminiProvider)
    nothing = get_llm_provider(_settings(LLM_PROVIDER="groq", GROQ_API_KEY=SecretStr(""), LLM_API_KEY=SecretStr("")))
    assert isinstance(nothing, MockLLMProvider)


def test_explicit_gemini_and_mock_selection_ignore_groq():
    gem = get_llm_provider(
        _settings(LLM_PROVIDER="gemini", GROQ_API_KEY=SecretStr(GROQ_KEY), LLM_API_KEY=SecretStr(GEMINI_KEY))
    )
    assert isinstance(gem, GeminiProvider)
    mock = get_llm_provider(_settings(LLM_PROVIDER="mock", GROQ_API_KEY=SecretStr(GROQ_KEY)))
    assert isinstance(mock, MockLLMProvider)


def test_provider_name_is_case_insensitive():
    assert isinstance(get_llm_provider(_settings(LLM_PROVIDER=" GROQ ", GROQ_API_KEY=SecretStr(GROQ_KEY))), GroqProvider)


# ----- fallback chain -----------------------------------------------------------------------


def test_chain_returns_groq_email_when_groq_works():
    gemini_calls = []

    def gemini_handler(request):
        gemini_calls.append(request)
        return _gemini_ok()(request)

    chain = FallbackLLMProvider([groq(_groq_ok()), gemini(gemini_handler)])
    email = chain.generate_email(LLMRequest("s", "u"))
    assert email.provider == "groq" and email.warning is None and email.subject == "Groq subject"
    assert gemini_calls == []  # Gemini is not called when Groq succeeds


def test_chain_falls_back_to_gemini_when_groq_fails(caplog):
    chain = FallbackLLMProvider([groq(_failing(503)), gemini(_gemini_ok())])
    with caplog.at_level(logging.WARNING):
        email = chain.generate_email(LLMRequest("s", "u"))
    assert email.provider == "gemini" and email.subject == "Gemini subject"
    assert "groq" in email.warning
    assert "LLM provider groq failed code=llm_error" in caplog.text
    assert GROQ_KEY not in caplog.text


def test_chain_raises_one_safe_error_when_all_fail():
    chain = FallbackLLMProvider([groq(_failing(500)), gemini(_failing(429))])
    with pytest.raises(LLMError) as info:
        chain.generate_email(LLMRequest("s", "u"))
    assert info.value.code == "llm_rate_limited"
    assert "groq" in info.value.message and "gemini" in info.value.message
    assert GROQ_KEY not in info.value.message and GEMINI_KEY not in info.value.message


# ----- through the API ----------------------------------------------------------------------


@pytest.fixture()
def company(client, auth_headers):
    create_company(client, auth_headers)
    return auth_headers


def _generate(client, headers, provider):
    app.dependency_overrides[get_llm] = lambda: provider
    try:
        return client.post(GENERATE, json=REQUEST, headers=headers)
    finally:
        app.dependency_overrides.pop(get_llm, None)


def test_api_reports_groq_without_fallback(client, company):
    seen = {}

    def handler(request):
        seen["prompt"] = json.loads(request.content)["messages"][1]["content"]
        return _groq_ok()(request)

    body = _generate(client, company, FallbackLLMProvider([groq(handler), gemini(_gemini_ok())])).json()
    assert body["provider"] == "groq" and body["fallback_used"] is False and body["warning"] is None
    assert body["subject"] == "Groq subject"
    # The same company context is sent to Groq as to any other provider.
    assert "ABC Technologies" in seen["prompt"] and "Introduce our CRM" in seen["prompt"]


def test_api_reports_gemini_fallback(client, company):
    body = _generate(client, company, FallbackLLMProvider([groq(_failing(503)), gemini(_gemini_ok())])).json()
    assert body["provider"] == "gemini" and body["fallback_used"] is True
    assert body["subject"] == "Gemini subject" and "groq" in body["warning"]


def test_api_uses_mock_when_groq_and_gemini_fail(client, company, caplog):
    with caplog.at_level(logging.DEBUG):
        response = _generate(client, company, FallbackLLMProvider([groq(_failing(401)), gemini(_failing(503))]))
    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "mock" and body["fallback_used"] is True and "ABC Technologies" in body["body"]
    for secret in (GROQ_KEY, GEMINI_KEY, "bad key"):
        assert secret not in response.text
        assert secret not in caplog.text


def test_api_returns_503_when_all_fail_and_mock_fallback_disabled(client, company, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_FALLBACK_TO_MOCK", False)
    response = _generate(client, company, FallbackLLMProvider([groq(_failing(500)), gemini(_failing(500))]))
    assert response.status_code == 503
    assert GROQ_KEY not in response.text and GEMINI_KEY not in response.text


def test_groq_key_is_redacted_if_it_ever_reaches_a_log_line():
    from app.core.logging import redact

    assert GROQ_KEY not in redact(f"calling groq with {GROQ_KEY}")
    assert GROQ_KEY not in redact(f"Authorization: Bearer {GROQ_KEY}")
