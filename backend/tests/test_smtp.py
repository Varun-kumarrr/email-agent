import logging
import smtplib
import socket
import ssl

import pytest

from app.services.smtp_client import SmtpCredentials, classify_error
from app.models.enums import SecurityType
from tests.fakes import install_fake_smtp
from tests.test_company import create_company
from tests.test_email_config import SMTP_PASSWORD, SMTP_SETTINGS, create_config

TEST = "/api/v1/email-config/test"


@pytest.fixture()
def smtp(monkeypatch):
    return install_fake_smtp(monkeypatch)


@pytest.fixture()
def configured(client, auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    return auth_headers


def test_successful_starttls_test(client, configured, smtp):
    response = client.post(TEST, json={"recipient": "check@example.com"}, headers=configured)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    conn = smtp.last
    assert (conn.host, conn.port, conn.ssl, conn.started_tls) == ("smtp.abctech.com", 587, False, True)
    assert conn.logged_in_as == "anjali@abctech.com"
    assert conn.password_used == SMTP_PASSWORD  # decrypted only for the SMTP login
    message = smtp.sent[0]
    assert message["To"] == "check@example.com"
    assert "anjali@abctech.com" in message["From"]
    assert SMTP_PASSWORD not in response.text

    config = client.get("/api/v1/email-config", headers=configured).json()
    assert config["last_test_success"] is True and config["last_tested_at"]


def test_ssl_tls_mode_uses_smtp_ssl(client, configured, smtp):
    client.put("/api/v1/email-config", json={**SMTP_SETTINGS, "security_type": "SSL_TLS", "smtp_port": 465}, headers=configured)
    assert client.post(TEST, json={"recipient": "c@example.com"}, headers=configured).json()["success"]
    assert smtp.last.ssl is True and smtp.last.started_tls is False


def test_none_mode_uses_plain_smtp(client, configured, smtp):
    client.put("/api/v1/email-config", json={**SMTP_SETTINGS, "security_type": "NONE", "smtp_port": 25}, headers=configured)
    assert client.post(TEST, json={"recipient": "c@example.com"}, headers=configured).json()["success"]
    assert smtp.last.ssl is False and smtp.last.started_tls is False


@pytest.mark.parametrize(
    ("step", "error", "code"),
    [
        ("login", smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"), "auth_failed"),
        ("connect", socket.gaierror(11001, "getaddrinfo failed"), "invalid_host"),
        ("connect", ConnectionRefusedError(10061, "refused"), "connection_refused"),
        ("connect", TimeoutError("timed out"), "timeout"),
        ("starttls", ssl.SSLError("wrong version number"), "tls_failed"),
        ("connect", ssl.SSLCertVerificationError("certificate verify failed"), "tls_certificate"),
        ("starttls", smtplib.SMTPNotSupportedError("STARTTLS extension not supported"), "starttls_unsupported"),
        ("send", smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no such user")}), "recipient_refused"),
        ("send", smtplib.SMTPDataError(554, b"rejected"), "smtp_error"),
    ],
)
def test_failures_return_safe_messages(client, configured, smtp, step, error, code):
    smtp.fail_on, smtp.error = step, error
    response = client.post(TEST, json={"recipient": "c@example.com"}, headers=configured)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == code
    assert SMTP_PASSWORD not in response.text
    assert "Traceback" not in response.text
    assert "Username and Password not accepted" not in response.text  # raw server text not exposed
    assert client.get("/api/v1/email-config", headers=configured).json()["last_test_success"] is False


def test_invalid_recipient_rejected_before_connecting(client, configured, smtp):
    response = client.post(TEST, json={"recipient": "not-an-email"}, headers=configured)
    assert response.status_code == 422
    assert smtp.connections == []


def test_test_requires_configuration(client, auth_headers, smtp):
    create_company(client, auth_headers)
    assert client.post(TEST, json={"recipient": "c@example.com"}, headers=auth_headers).status_code == 404


def test_smtp_failure_logs_do_not_contain_password(client, configured, smtp, caplog):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, b"bad credentials")
    with caplog.at_level(logging.DEBUG):
        client.post(TEST, json={"recipient": "c@example.com"}, headers=configured)
    assert "auth_failed" in caplog.text
    assert SMTP_PASSWORD not in caplog.text


def test_credentials_repr_hides_password():
    creds = SmtpCredentials("h", 587, "u", "p@ss-secret", SecurityType.STARTTLS)
    assert "p@ss-secret" not in repr(creds)


def test_transient_classification():
    assert classify_error(TimeoutError()).transient is True
    assert classify_error(smtplib.SMTPServerDisconnected()).transient is True
    assert classify_error(smtplib.SMTPDataError(451, b"try later")).transient is True
    assert classify_error(smtplib.SMTPAuthenticationError(535, b"no")).transient is False
