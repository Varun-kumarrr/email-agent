import pytest

from app.core.config import settings
from app.core.dependencies import get_llm
from app.main import app
from app.services.llm import LLMError, MockLLMProvider
from tests.fakes import RecordingLLM
from tests.test_company import create_company
from tests.test_email_config import SMTP_PASSWORD, create_config
from tests.test_isolation import XYZ_PROFILE
from tests.test_signature import PAYLOAD as SIGNATURE_PAYLOAD

GENERATE = "/api/v1/agent/generate-email"
REQUEST = {
    "recipient_name": "Priya",
    "recipient_email": "priya@smallbiz.in",
    "purpose": "Write a professional cold email introducing our CRM to a small business owner.",
    "tone": "professional",
    "additional_instructions": "Keep it under 150 words.",
}


@pytest.fixture()
def llm():
    fake = RecordingLLM()
    app.dependency_overrides[get_llm] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm, None)


@pytest.fixture()
def full_profile(client, auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    client.post("/api/v1/signature", json=SIGNATURE_PAYLOAD, headers=auth_headers)
    return auth_headers


def test_generation_returns_subject_and_body(client, full_profile, llm):
    response = client.post(GENERATE, json=REQUEST, headers=full_profile)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subject"] == "Generated subject"
    assert body["body"].startswith("Hi Priya")
    assert body["provider"] == "recording"
    assert body["fallback_used"] is False


def test_context_contains_all_company_information(client, full_profile, llm):
    client.post(GENERATE, json=REQUEST, headers=full_profile)
    prompt = llm.last.user_prompt
    for expected in [
        "ABC Technologies",
        "AI-powered CRM solutions for small and medium-sized businesses.",
        "Sales automation",
        "Analytics",
        "Small and medium-sized businesses",
        "Reduce manual sales work and improve productivity.",
        "anjali@abctech.com",  # contact / sender email
        "+91 98765 43210",  # contact phone
        "Anjali from ABC Technologies",  # sender identity
        "Business Development Manager",  # signature
        "Priya",
        "introducing our CRM",
        "Keep it under 150 words.",
    ]:
        assert expected in prompt, expected
    assert "Do not invent" in llm.last.system_prompt


def test_generation_does_not_leak_smtp_password_to_llm(client, full_profile, llm):
    client.post(GENERATE, json=REQUEST, headers=full_profile)
    assert SMTP_PASSWORD not in llm.last.user_prompt
    assert SMTP_PASSWORD not in llm.last.system_prompt
    assert SMTP_PASSWORD not in str(llm.last.context)


def test_mock_provider_end_to_end(client, full_profile):
    app.dependency_overrides[get_llm] = lambda: MockLLMProvider()
    try:
        body = client.post(GENERATE, json=REQUEST, headers=full_profile).json()
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert body["provider"] == "mock"
    assert "ABC Technologies" in body["body"]
    assert "CRM, Sales automation and Analytics" in body["body"]


def test_default_provider_without_api_key_is_mock(client, full_profile):
    body = client.post(GENERATE, json=REQUEST, headers=full_profile).json()
    assert body["provider"] == "mock"


def test_provider_failure_falls_back_to_mock(client, full_profile, llm, monkeypatch):
    monkeypatch.setattr(settings, "LLM_FALLBACK_TO_MOCK", True)
    llm.error = LLMError("AI provider rate limit or free-tier quota reached. Try again later.", code="llm_rate_limited")
    body = client.post(GENERATE, json=REQUEST, headers=full_profile).json()
    assert body["fallback_used"] is True
    assert body["provider"] == "mock"
    assert "quota" in body["warning"]
    assert "ABC Technologies" in body["body"]


def test_provider_failure_without_fallback_is_503(client, full_profile, llm, monkeypatch):
    monkeypatch.setattr(settings, "LLM_FALLBACK_TO_MOCK", False)
    llm.error = LLMError("Could not reach the AI provider.", code="llm_unreachable")
    response = client.post(GENERATE, json=REQUEST, headers=full_profile)
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"code": "llm_unreachable"}


def test_generation_validation(client, full_profile, llm):
    for payload in [
        {**REQUEST, "recipient_email": "bad"},
        {**REQUEST, "purpose": ""},
        {**REQUEST, "tone": "angry"},
        {**REQUEST, "recipient_name": ""},
    ]:
        assert client.post(GENERATE, json=payload, headers=full_profile).status_code == 422
    assert llm.requests == []


def test_generation_requires_company(client, auth_headers, llm):
    assert client.post(GENERATE, json=REQUEST, headers=auth_headers).status_code == 404
    assert client.post(GENERATE, json=REQUEST).status_code == 401


def test_generation_uses_only_own_company_context(client, full_profile, other_auth_headers, llm):
    create_company(client, other_auth_headers, XYZ_PROFILE)
    client.post(GENERATE, json=REQUEST, headers=other_auth_headers)
    prompt = llm.last.user_prompt
    assert "XYZ Corp" in prompt
    assert "ABC Technologies" not in prompt
    assert "Business Development Manager" not in prompt  # the other company's signature
