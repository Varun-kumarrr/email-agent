"""Gmail SMTP and generic/public SMTP delivery (against the fake SMTP server).

Real provider delivery is tested manually with the user's own credentials (see README);
these tests prove the exact connection settings, TLS mode, login and message content used.
"""

import smtplib

import pytest

from app.core.encryption import decrypt_secret
from app.models import EmailAccount
from tests.fakes import install_fake_smtp
from tests.test_company import create_company

ACCOUNTS = "/api/v1/email-accounts"
SEND = "/api/v1/emails/send"

GMAIL = {
    "account_name": "Gmail",
    "provider": "GMAIL",
    "email_address": "sales.abctech@gmail.com",
    "sender_name": "ABC Sales",
    "reply_to": "replies@abctech.com",
    "password": "abcd efgh ijkl mnop",  # the format Google displays App Passwords in
}


@pytest.fixture()
def smtp(monkeypatch):
    return install_fake_smtp(monkeypatch)


@pytest.fixture()
def company(client, auth_headers):
    create_company(client, auth_headers)
    client.post(
        "/api/v1/signature",
        json={"signature_text": "Best Regards,\nAnjali\nABC Technologies", "enabled": True, "append_automatically": True},
        headers=auth_headers,
    )
    return auth_headers


def test_gmail_uses_starttls_587_and_app_password_without_spaces(client, company, smtp, db_session):
    account = client.post(ACCOUNTS, json=GMAIL, headers=company).json()
    stored = db_session.get(EmailAccount, __import__("uuid").UUID(account["id"]))
    assert decrypt_secret(stored.encrypted_smtp_password) == "abcdefghijklmnop"

    result = client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "owner@example.com"}, headers=company).json()
    assert result["success"] is True
    conn = smtp.last
    assert (conn.host, conn.port, conn.ssl, conn.started_tls) == ("smtp.gmail.com", 587, False, True)
    assert (conn.logged_in_as, conn.password_used) == ("sales.abctech@gmail.com", "abcdefghijklmnop")


def test_gmail_ssl_465_variant(client, company, smtp):
    account = client.post(ACCOUNTS, json={**GMAIL, "smtp_port": 465, "security_type": "SSL_TLS"}, headers=company).json()
    client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "owner@example.com"}, headers=company)
    assert (smtp.last.host, smtp.last.port, smtp.last.ssl) == ("smtp.gmail.com", 465, True)


def test_gmail_send_full_message(client, company, smtp):
    account = client.post(ACCOUNTS, json=GMAIL, headers=company).json()
    body = client.post(
        SEND,
        json={
            "recipient": "priya@example.com",
            "subject": "CRM demo",
            "body": "Hi Priya,\n\nShort note.\n\nBest regards,",
            "format": "HTML",
            "cc": ["cc@example.com"],
            "bcc": ["hidden@example.com"],
            "email_account_id": account["id"],
        },
        headers=company,
    ).json()
    assert body["status"] == "SENT"
    message = smtp.sent[-1]
    assert message["From"] == "ABC Sales <sales.abctech@gmail.com>"
    assert message["Reply-To"] == "replies@abctech.com"
    assert message["Cc"] == "cc@example.com" and message["Bcc"] is None
    assert smtp.envelopes[-1] == ["priya@example.com", "cc@example.com", "hidden@example.com"]
    text = message.get_body(preferencelist=("plain",)).get_content()
    html_part = message.get_body(preferencelist=("html",)).get_content()
    assert text.count("ABC Technologies") == 1 and text.lower().count("regards") == 1
    assert "<p>Hi Priya,</p>" in html_part


def test_gmail_auth_failure_explains_app_password(client, company, smtp):
    smtp.fail_on = "login"
    smtp.error = smtplib.SMTPAuthenticationError(534, b"5.7.9 Application-specific password required.")
    account = client.post(ACCOUNTS, json=GMAIL, headers=company).json()
    result = client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "o@example.com"}, headers=company).json()
    assert result["success"] is False and result["error_code"] == "auth_failed"
    assert "App Password" in result["message"]
    assert "5.7.9" not in result["message"] and "abcdefghijklmnop" not in result["message"]


def test_outlook_auth_failure_explains_smtp_auth(client, company, smtp):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, b"5.7.139 Authentication unsuccessful")
    account = client.post(
        ACCOUNTS,
        json={**GMAIL, "provider": "OUTLOOK", "email_address": "sales@abctech.onmicrosoft.com", "password": "pw-123456"},
        headers=company,
    ).json()
    assert account["smtp_host"] == "smtp.office365.com"
    result = client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "o@example.com"}, headers=company).json()
    assert "SMTP AUTH" in result["message"]


def test_gmail_auth_hint_also_in_history_on_send(client, company, smtp):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, b"bad")
    account = client.post(ACCOUNTS, json=GMAIL, headers=company).json()
    response = client.post(
        SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b", "email_account_id": account["id"]}, headers=company
    )
    assert response.status_code == 502
    item = client.get("/api/v1/emails/history", headers=company).json()["items"][0]
    assert "App Password" in item["error_message"] and item["error_code"] == "auth_failed"


@pytest.mark.parametrize(
    ("host", "port", "security", "expect_ssl", "expect_tls"),
    [
        ("smtp.zoho.com", 465, "SSL_TLS", True, False),
        ("sandbox.smtp.mailtrap.io", 587, "STARTTLS", False, True),
        ("mail.example-host.com", 2525, "STARTTLS", False, True),
        ("relay.example.net", 25, "NONE", False, False),
    ],
)
def test_generic_public_smtp_providers(client, company, smtp, host, port, security, expect_ssl, expect_tls):
    account = client.post(
        ACCOUNTS,
        json={
            "account_name": host, "provider": "GENERIC", "email_address": "news@abctech.com", "sender_name": "ABC",
            "smtp_host": host, "smtp_port": port, "security_type": security, "smtp_username": "apikey-user",
            "password": "provider-password",
        },
        headers=company,
    ).json()
    result = client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "o@example.com"}, headers=company).json()
    assert result["success"] is True
    conn = smtp.last
    assert (conn.host, conn.port, conn.ssl, conn.started_tls) == (host, port, expect_ssl, expect_tls)
    assert (conn.logged_in_as, conn.password_used) == ("apikey-user", "provider-password")


def test_generic_password_spaces_are_preserved(client, company, db_session):
    account = client.post(
        ACCOUNTS,
        json={
            "account_name": "g", "provider": "GENERIC", "email_address": "g@abctech.com", "sender_name": "G",
            "smtp_host": "smtp.example.com", "smtp_port": 587, "security_type": "STARTTLS", "password": "pass with spaces",
        },
        headers=company,
    ).json()
    stored = db_session.get(EmailAccount, __import__("uuid").UUID(account["id"]))
    assert decrypt_secret(stored.encrypted_smtp_password) == "pass with spaces"
