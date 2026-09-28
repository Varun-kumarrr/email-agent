import smtplib
import uuid

import pytest

from tests.fakes import install_fake_smtp
from tests.test_company import create_company
from tests.test_email_config import SMTP_PASSWORD, create_config
from tests.test_email_sending import EMAIL, SEND
from tests.test_isolation import XYZ_PROFILE, XYZ_SMTP

HISTORY = "/api/v1/emails/history"


@pytest.fixture()
def smtp(monkeypatch):
    return install_fake_smtp(monkeypatch)


@pytest.fixture()
def sender(client, auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    return auth_headers


def test_successful_email_recorded(client, sender, smtp):
    client.post(SEND, json={**EMAIL, "cc": ["cc@example.com"]}, headers=sender)
    page = client.get(HISTORY, headers=sender).json()
    assert page["total"] == 1
    item = page["items"][0]
    assert item["status"] == "SENT"
    assert item["sender_email"] == "anjali@abctech.com"
    assert item["recipient"] == "priya@smallbiz.in"
    assert item["subject"] == EMAIL["subject"]
    assert item["email_format"] == "PLAIN_TEXT"
    assert item["cc"] == ["cc@example.com"]
    assert item["sent_at"] and item["created_at"]
    assert item["error_message"] is None


def test_failed_email_recorded_with_safe_reason(client, sender, smtp):
    smtp.fail_on, smtp.error = "connect", ConnectionRefusedError()
    client.post(SEND, json=EMAIL, headers=sender)
    item = client.get(HISTORY, headers=sender).json()["items"][0]
    assert item["status"] == "FAILED"
    assert item["sent_at"] is None
    assert item["error_message"] == "Connection refused. Check the SMTP host and port."


def test_history_contains_no_secrets(client, sender, smtp):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, SMTP_PASSWORD.encode())
    client.post(SEND, json=EMAIL, headers=sender)
    client.post(SEND, json={**EMAIL, "subject": "second"}, headers=sender)
    response = client.get(HISTORY, headers=sender)
    text = response.text
    assert SMTP_PASSWORD not in text
    assert sender["Authorization"].split()[1] not in text
    for forbidden in ("password", "encrypted", "token", "api_key"):
        assert forbidden not in response.json()["items"][0]


def test_pagination_and_status_filter(client, sender, smtp):
    for i in range(5):
        client.post(SEND, json={**EMAIL, "subject": f"Email {i}"}, headers=sender)
    smtp.fail_on, smtp.error = "connect", ConnectionRefusedError()
    client.post(SEND, json={**EMAIL, "subject": "Failed one"}, headers=sender)

    page1 = client.get(HISTORY, params={"page": 1, "page_size": 4}, headers=sender).json()
    page2 = client.get(HISTORY, params={"page": 2, "page_size": 4}, headers=sender).json()
    assert page1["total"] == 6 and page1["pages"] == 2
    assert len(page1["items"]) == 4 and len(page2["items"]) == 2
    assert page1["items"][0]["subject"] == "Failed one"  # newest first

    failed = client.get(HISTORY, params={"status": "FAILED"}, headers=sender).json()
    assert failed["total"] == 1
    assert client.get(HISTORY, params={"page_size": 500}, headers=sender).status_code == 422


def test_get_single_record(client, sender, smtp):
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    response = client.get(f"{HISTORY}/{history_id}", headers=sender)
    assert response.status_code == 200
    assert response.json()["body"].startswith("Hi Priya")
    assert client.get(f"{HISTORY}/{uuid.uuid4()}", headers=sender).status_code == 404


def test_history_is_isolated_between_companies(client, sender, other_auth_headers, smtp):
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    create_company(client, other_auth_headers, XYZ_PROFILE)
    create_config(client, other_auth_headers, XYZ_SMTP)

    assert client.get(HISTORY, headers=other_auth_headers).json()["total"] == 0
    # Knowing the ID of another company's record does not help.
    assert client.get(f"{HISTORY}/{history_id}", headers=other_auth_headers).status_code == 404
    assert client.get(HISTORY, headers=sender).json()["total"] == 1


def test_history_requires_auth(client):
    assert client.get(HISTORY).status_code == 401
