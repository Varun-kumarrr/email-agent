"""Security checks that span the whole application."""

import logging
import smtplib

import httpx

from app.core.dependencies import get_llm
from app.main import app
from app.services.llm import GeminiProvider
from tests.conftest import DEFAULT_PASSWORD, register_and_login
from tests.fakes import install_fake_smtp
from tests.test_company import ABC_PROFILE
from tests.test_email_config import SMTP_PASSWORD, SMTP_SETTINGS

GEMINI_KEY = "AIza" + "FAKE_GEMINI_KEY_FOR_SECURITY_TESTS"


def test_no_secrets_in_logs_or_responses_across_full_flow(client, monkeypatch, caplog):
    smtp = install_fake_smtp(monkeypatch)
    failing_gemini = GeminiProvider(
        GEMINI_KEY, "gemini-2.5-flash", transport=httpx.MockTransport(lambda r: httpx.Response(429))
    )
    app.dependency_overrides[get_llm] = lambda: failing_gemini
    responses = []
    try:
        with caplog.at_level(logging.DEBUG):
            headers = register_and_login(client)
            token = headers["Authorization"].split()[1]
            responses.append(client.post("/api/v1/company", json=ABC_PROFILE, headers=headers))
            responses.append(client.post("/api/v1/email-config", json=SMTP_SETTINGS, headers=headers))
            responses.append(client.get("/api/v1/email-config", headers=headers))
            responses.append(client.put("/api/v1/email-config", json=SMTP_SETTINGS, headers=headers))
            responses.append(
                client.post(
                    "/api/v1/agent/generate-email",
                    json={"recipient_name": "P", "recipient_email": "p@example.com", "purpose": "Intro"},
                    headers=headers,
                )
            )
            smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, SMTP_PASSWORD.encode())
            responses.append(
                client.post("/api/v1/emails/send", json={"recipient": "p@example.com", "subject": "s", "body": "b"}, headers=headers)
            )
            responses.append(client.get("/api/v1/emails/history", headers=headers))
            responses.append(client.get("/api/v1/preferences", headers=headers))
    finally:
        app.dependency_overrides.pop(get_llm, None)

    secrets = [SMTP_PASSWORD, DEFAULT_PASSWORD, GEMINI_KEY, token, "test-secret-key-that-is-only-used-in-tests"]
    for response in responses:
        for secret in secrets:
            assert secret not in response.text, (response.request.url, secret)
    for secret in secrets:
        assert secret not in caplog.text, secret
    # The generation fell back to the mock after the (fake) Gemini quota error.
    assert responses[4].json()["fallback_used"] is True


def test_password_hash_is_bcrypt_and_never_exposed(client, db_session):
    from app.models import User

    register_and_login(client)
    user = db_session.query(User).one()
    assert user.hashed_password.startswith("$2") and DEFAULT_PASSWORD not in user.hashed_password
    me = client.post("/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}).json()
    assert user.hashed_password not in str(me)


def test_sql_injection_payloads_are_treated_as_data(client):
    payload = "x'; DROP TABLE users; --@example.com"
    response = client.post("/api/v1/auth/login", json={"email": payload, "password": "x"})
    assert response.status_code == 422  # rejected by validation, never reaches SQL
    response = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "' OR '1'='1"})
    assert response.status_code == 401
    headers = register_and_login(client)
    name = "Robert'); DROP TABLE companies;--"
    created = client.post("/api/v1/company", json={**ABC_PROFILE, "name": name}, headers=headers)
    assert created.status_code == 201
    assert client.get("/api/v1/company", headers=headers).json()["name"] == name  # stored verbatim, parameterized


def test_none_algorithm_token_rejected(client):
    import base64
    import json

    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    register_and_login(client)
    forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': 'x', 'exp': 9999999999, 'type': 'access'})}."
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
