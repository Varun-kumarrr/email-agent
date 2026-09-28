import socket

import pytest
from pydantic import SecretStr

from app.core.config import Settings, settings, validate_production_settings
from tests.conftest import DEFAULT_PASSWORD, register_and_login
from tests.fakes import install_fake_smtp
from tests.test_agent import REQUEST as GENERATE_REQUEST
from tests.test_company import create_company
from tests.test_email_config import SMTP_SETTINGS, create_config


def test_login_rate_limited(client):
    register_and_login(client)
    for _ in range(9):  # register_and_login already used one attempt
        client.post("/api/v1/auth/login", json={"email": "anjali@abctech.com", "password": "Wrong1234"})
    response = client.post("/api/v1/auth/login", json={"email": "anjali@abctech.com", "password": DEFAULT_PASSWORD})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert "retry-after" in response.headers
    # Another account from the same client is not locked out.
    other = client.post("/api/v1/auth/login", json={"email": "someone@example.com", "password": "Wrong1234"})
    assert other.status_code == 401


def test_generation_rate_limited(client, auth_headers):
    create_company(client, auth_headers)
    codes = [client.post("/api/v1/agent/generate-email", json=GENERATE_REQUEST, headers=auth_headers).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30
    assert codes[30] == 429


def test_security_headers(client):
    response = client.get("/api/v1/auth/me")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def _prod(**overrides):
    base = dict(
        ENVIRONMENT="production",
        SECRET_KEY=SecretStr("x" * 48),
        ENCRYPTION_KEY=SecretStr("fernet-key-placeholder"),
        ALLOWED_ORIGINS=["https://app.example.com"],
        SMTP_ALLOW_PRIVATE_HOSTS=False,
        FRONTEND_URL="https://app.example.com",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_production_settings_validation():
    validate_production_settings(_prod())  # safe config passes
    for unsafe in [
        {"SECRET_KEY": SecretStr("change-me-in-your-local-env-file")},
        {"SECRET_KEY": SecretStr("short")},
        {"ENCRYPTION_KEY": SecretStr("")},
        {"ALLOWED_ORIGINS": ["*"]},
        {"SMTP_ALLOW_PRIVATE_HOSTS": True},
        {"FRONTEND_URL": "http://app.example.com"},
        {"GOOGLE_CLIENT_ID": "id", "GOOGLE_REDIRECT_URI": "http://app.example.com/cb"},
    ]:
        with pytest.raises(RuntimeError):
            validate_production_settings(_prod(**unsafe))
    validate_production_settings(Settings(_env_file=None, ENVIRONMENT="development"))  # dev is lenient


@pytest.fixture()
def configured(client, auth_headers, monkeypatch):
    install_fake_smtp(monkeypatch)
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    return auth_headers


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "::1"])
def test_private_smtp_hosts_blocked_when_disabled(client, configured, monkeypatch, address):
    monkeypatch.setattr(settings, "SMTP_ALLOW_PRIVATE_HOSTS", False)
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(family, socket.SOCK_STREAM, 6, "", (address, 587))])
    body = client.post("/api/v1/email-config/test", json={"recipient": "c@example.com"}, headers=configured).json()
    assert body["success"] is False
    assert body["error_code"] == "host_not_allowed"


def test_public_smtp_host_allowed_when_private_disabled(client, configured, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_ALLOW_PRIVATE_HOSTS", False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 587))])
    body = client.post("/api/v1/email-config/test", json={"recipient": "c@example.com"}, headers=configured).json()
    assert body["success"] is True


def test_private_hosts_allowed_in_development_default(client, configured):
    assert settings.SMTP_ALLOW_PRIVATE_HOSTS is True
    client.put("/api/v1/email-config", json={**SMTP_SETTINGS, "smtp_host": "localhost"}, headers=configured)
    body = client.post("/api/v1/email-config/test", json={"recipient": "c@example.com"}, headers=configured).json()
    assert body["success"] is True
