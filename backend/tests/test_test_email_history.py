"""The account Test action records the test email in the history, marked is_test=True."""

import smtplib
import uuid

import pytest

from app.models import EmailHistory, EmailStatus
from tests.fake_google import install_fake_google
from tests.fakes import install_fake_smtp
from tests.test_company import create_company
from tests.test_email_config import SMTP_PASSWORD, SMTP_SETTINGS, create_config
from tests.test_gmail_oauth import connect
from tests.test_isolation import XYZ_PROFILE

ACCOUNTS = "/api/v1/email-accounts"
HISTORY = "/api/v1/emails/history"
SMTP_ACCOUNT = {
    "account_name": "Support", "provider": "GENERIC", "email_address": "support@abctech.com",
    "sender_name": "ABC Support", "reply_to": "replies@abctech.com", "smtp_host": "smtp.zoho.com",
    "smtp_port": 465, "security_type": "SSL_TLS", "password": SMTP_PASSWORD,
}


@pytest.fixture()
def smtp(monkeypatch):
    return install_fake_smtp(monkeypatch)


@pytest.fixture()
def company(client, auth_headers):
    create_company(client, auth_headers)
    return auth_headers


def _history(client, headers):
    return client.get(HISTORY, headers=headers).json()


def test_smtp_account_test_is_recorded_as_test_email(client, company, smtp, db_session):
    account = client.post(ACCOUNTS, json=SMTP_ACCOUNT, headers=company).json()
    result = client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "Owner@Example.com"}, headers=company).json()
    assert result["success"] is True

    page = _history(client, company)
    assert page["total"] == 1
    item = page["items"][0]
    assert item["is_test"] is True and item["status"] == "SENT"
    assert item["email_account_id"] == account["id"]
    assert item["sender_email"] == "support@abctech.com" and item["sender_name"] == "ABC Support"
    assert item["reply_to"] == "replies@abctech.com" and item["recipient"] == "owner@example.com"
    assert item["subject"] == "Email Agent: email account test"
    assert "working correctly" in item["body"] and item["attempts"] == 1 and item["sent_at"]
    # The row matches what was actually sent.
    assert smtp.sent[-1]["Subject"] == item["subject"]
    record = db_session.get(EmailHistory, uuid.UUID(item["id"]))
    assert record.sent_by_user_id is not None  # the user who clicked Test


def test_failed_smtp_test_is_recorded_with_safe_reason(client, company, smtp):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, SMTP_PASSWORD.encode())
    account = client.post(ACCOUNTS, json=SMTP_ACCOUNT, headers=company).json()
    result = client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "o@example.com"}, headers=company).json()
    assert result["success"] is False
    item = _history(client, company)["items"][0]
    assert item["is_test"] is True and item["status"] == "FAILED"
    assert item["error_code"] == "auth_failed" and item["sent_at"] is None
    assert item["error_message"] == result["message"]  # the same safe message as the Test result


def test_last_test_behaviour_is_preserved(client, company, smtp):
    account = client.post(ACCOUNTS, json=SMTP_ACCOUNT, headers=company).json()
    client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "o@example.com"}, headers=company)
    fetched = client.get(f"{ACCOUNTS}/{account['id']}", headers=company).json()
    assert fetched["last_test_success"] is True and fetched["last_tested_at"]


def test_legacy_email_config_test_is_recorded(client, company, smtp):
    create_config(client, company)
    client.post("/api/v1/email-config/test", json={"recipient": "o@example.com"}, headers=company)
    item = _history(client, company)["items"][0]
    assert item["is_test"] is True and item["sender_email"] == SMTP_SETTINGS["email"]


def test_gmail_oauth_account_test_is_recorded_as_test_email(client, company, monkeypatch):
    google = install_fake_google(monkeypatch)
    oauth = connect(client, company)
    result = client.post(f"{ACCOUNTS}/{oauth['id']}/test", json={"recipient": "owner@example.com"}, headers=company).json()
    assert result["success"] is True
    item = _history(client, company)["items"][0]
    assert item["is_test"] is True and item["status"] == "SENT"
    assert item["email_account_id"] == oauth["id"] and item["sender_email"] == "sales.abctech@gmail.com"
    assert google.sent[-1]["message"]["Subject"] == item["subject"]


def test_failed_gmail_oauth_test_is_recorded(client, company, monkeypatch):
    google = install_fake_google(monkeypatch)
    oauth = connect(client, company)
    google.send_statuses = [403]
    client.post(f"{ACCOUNTS}/{oauth['id']}/test", json={"recipient": "o@example.com"}, headers=company)
    item = _history(client, company)["items"][0]
    assert item["is_test"] is True and item["status"] == "FAILED" and item["error_code"] == "gmail_forbidden"


def test_test_history_contains_no_credentials(client, company, monkeypatch, smtp):
    install_fake_google(monkeypatch)
    oauth = connect(client, company)
    smtp_account = client.post(ACCOUNTS, json=SMTP_ACCOUNT, headers=company).json()
    for account_id in (oauth["id"], smtp_account["id"]):
        client.post(f"{ACCOUNTS}/{account_id}/test", json={"recipient": "o@example.com"}, headers=company)
    response = client.get(HISTORY, headers=company)
    assert response.json()["total"] == 2
    for secret in (SMTP_PASSWORD, "fake-access-token", "fake-refresh-token", "test-client-secret-value", "encrypted", "gAAAA"):
        assert secret not in response.text
    for item in response.json()["items"]:
        assert not {"password", "encrypted_smtp_password", "encrypted_oauth_access_token", "encrypted_oauth_refresh_token"} & item.keys()


def test_test_emails_do_not_use_the_daily_limit(client, company, smtp):
    account = client.post(ACCOUNTS, json=SMTP_ACCOUNT, headers=company).json()
    for _ in range(3):
        client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "o@example.com"}, headers=company)
    prefs = client.get("/api/v1/preferences", headers=company).json()
    assert prefs["sent_today"] == 0


def test_real_emails_are_not_marked_as_tests(client, company, smtp):
    client.post(ACCOUNTS, json=SMTP_ACCOUNT, headers=company)
    client.post("/api/v1/emails/send", json={"recipient": "p@example.com", "subject": "s", "body": "b"}, headers=company)
    assert _history(client, company)["items"][0]["is_test"] is False


def test_test_history_is_company_scoped(client, company, other_auth_headers, smtp):
    account = client.post(ACCOUNTS, json=SMTP_ACCOUNT, headers=company).json()
    client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "o@example.com"}, headers=company)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    assert _history(client, other_auth_headers)["total"] == 0
    item_id = _history(client, company)["items"][0]["id"]
    assert client.get(f"{HISTORY}/{item_id}", headers=other_auth_headers).status_code == 404


def test_existing_rows_default_to_real_emails(db_session, client, company, smtp):
    client.post(ACCOUNTS, json=SMTP_ACCOUNT, headers=company)
    client.post("/api/v1/emails/send", json={"recipient": "p@example.com", "subject": "s", "body": "b"}, headers=company)
    record = db_session.query(EmailHistory).one()
    assert record.is_test is False and record.status == EmailStatus.SENT
