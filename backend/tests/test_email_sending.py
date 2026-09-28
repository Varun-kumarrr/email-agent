import smtplib

import pytest

from app.models import EmailHistory, EmailStatus
from app.schemas.signature import EXAMPLE_SIGNATURE
from tests.fakes import install_fake_smtp
from tests.test_company import create_company
from tests.test_email_config import SMTP_PASSWORD, SMTP_SETTINGS, create_config
from tests.test_isolation import XYZ_PROFILE, XYZ_SMTP
from tests.test_preferences import UPDATE as PREFS_UPDATE

SEND = "/api/v1/emails/send"
EMAIL = {
    "recipient": "priya@smallbiz.in",
    "subject": "Less manual sales work for your business",
    "body": "Hi Priya,\n\nI'd love to show you our CRM.\n\nBest regards,",
}


@pytest.fixture()
def smtp(monkeypatch):
    return install_fake_smtp(monkeypatch)


@pytest.fixture()
def sender(client, auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    return auth_headers


def _signature(client, headers, append=True, enabled=True):
    client.post(
        "/api/v1/signature",
        json={"signature_text": EXAMPLE_SIGNATURE, "enabled": enabled, "append_automatically": append},
        headers=headers,
    )


def test_successful_plain_text_send(client, sender, smtp, db_session):
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "SENT"
    assert body["sender_email"] == "anjali@abctech.com"
    assert body["format"] == "PLAIN_TEXT"
    assert SMTP_PASSWORD not in response.text

    message = smtp.sent[0]
    assert message["From"] == "Anjali from ABC Technologies <anjali@abctech.com>"
    assert message["To"] == "priya@smallbiz.in"
    assert message["Reply-To"] == "sales@abctech.com"
    assert message.get_content_type() == "text/plain"
    assert "show you our CRM" in message.get_content()
    assert smtp.last.logged_in_as == "anjali@abctech.com"

    record = db_session.query(EmailHistory).one()
    assert record.status == EmailStatus.SENT and record.attempts == 1


def test_html_send_has_plain_alternative_and_escapes_text(client, sender, smtp):
    email = {**EMAIL, "format": "HTML", "body": "Hi <Priya>,\n\nLine one\nLine two"}
    assert client.post(SEND, json=email, headers=sender).status_code == 200
    message = smtp.sent[0]
    assert message.get_content_type() == "multipart/alternative"
    html_part = message.get_body(preferencelist=("html",)).get_content()
    text_part = message.get_body(preferencelist=("plain",)).get_content()
    assert "&lt;Priya&gt;" in html_part and "Line one<br>Line two" in html_part
    assert "Hi <Priya>," in text_part


def test_html_body_written_as_html_is_kept(client, sender, smtp):
    email = {**EMAIL, "format": "HTML", "body": "<p>Hello <strong>Priya</strong></p>"}
    client.post(SEND, json=email, headers=sender)
    html_part = smtp.sent[0].get_body(preferencelist=("html",)).get_content()
    assert "<strong>Priya</strong>" in html_part


def test_default_format_from_preferences(client, sender, smtp):
    client.put("/api/v1/preferences", json={**PREFS_UPDATE, "default_cc": [], "default_bcc": []}, headers=sender)
    body = client.post(SEND, json=EMAIL, headers=sender).json()
    assert body["format"] == "HTML"


def test_signature_appended_automatically(client, sender, smtp):
    _signature(client, sender, append=True)
    body = client.post(SEND, json=EMAIL, headers=sender).json()
    assert body["signature_appended"] is True
    content = smtp.sent[0].get_content()
    assert content.rstrip().endswith("Website: www.abctech.com")
    assert content.count("Business Development Manager") == 1


def test_duplicate_sign_off_removed_when_signature_has_one(client, sender, smtp, db_session):
    _signature(client, sender, append=True)  # EXAMPLE_SIGNATURE starts with "Best Regards,"
    client.post(SEND, json=EMAIL, headers=sender)  # EMAIL body ends with "Best regards,"
    content = smtp.sent[0].get_content()
    assert content.lower().count("regards") == 1
    record = db_session.query(EmailHistory).one()
    assert record.body.lower().count("regards") == 1


def test_signature_not_duplicated_if_already_in_body(client, sender, smtp):
    _signature(client, sender, append=True)
    email = {**EMAIL, "body": EMAIL["body"] + "\n\n" + EXAMPLE_SIGNATURE}
    body = client.post(SEND, json=email, headers=sender).json()
    assert body["signature_appended"] is False
    assert smtp.sent[0].get_content().count("Business Development Manager") == 1


def test_signature_respects_settings_and_override(client, sender, smtp):
    _signature(client, sender, append=False)
    assert client.post(SEND, json=EMAIL, headers=sender).json()["signature_appended"] is False
    assert client.post(SEND, json={**EMAIL, "append_signature": True}, headers=sender).json()["signature_appended"] is True

    client.put("/api/v1/signature", json={"signature_text": "Sig", "enabled": False, "append_automatically": True}, headers=sender)
    assert client.post(SEND, json={**EMAIL, "append_signature": True}, headers=sender).json()["signature_appended"] is False


def test_cc_and_bcc(client, sender, smtp):
    email = {**EMAIL, "cc": ["cc1@example.com"], "bcc": ["hidden@example.com"]}
    body = client.post(SEND, json=email, headers=sender).json()
    assert body["cc"] == ["cc1@example.com"] and body["bcc"] == ["hidden@example.com"]
    message = smtp.sent[0]
    assert message["Cc"] == "cc1@example.com"
    assert message["Bcc"] is None  # BCC never appears in headers
    assert "hidden@example.com" not in message.as_string()
    assert smtp.envelopes[0] == ["priya@smallbiz.in", "cc1@example.com", "hidden@example.com"]


def test_default_cc_bcc_and_sender_overrides_from_preferences(client, sender, smtp):
    client.put("/api/v1/preferences", json={**PREFS_UPDATE, "default_format": "PLAIN_TEXT"}, headers=sender)
    client.post(SEND, json=EMAIL, headers=sender)
    message = smtp.sent[0]
    assert message["Cc"] == "manager@abctech.com"
    assert smtp.envelopes[0] == ["priya@smallbiz.in", "manager@abctech.com", "crm-log@abctech.com"]
    assert message["From"] == "ABC Sales Team <anjali@abctech.com>"  # name overridden, address is the SMTP account

    client.post(SEND, json={**EMAIL, "cc": [], "bcc": []}, headers=sender)
    assert smtp.envelopes[1] == ["priya@smallbiz.in"]


def test_smtp_failure_is_recorded_and_safe(client, sender, smtp, db_session):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, b"5.7.8 bad password for user")
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "email_send_failed"
    assert error["details"]["error_code"] == "auth_failed"
    assert SMTP_PASSWORD not in response.text
    assert "bad password for user" not in response.text

    record = db_session.query(EmailHistory).one()
    assert record.status == EmailStatus.FAILED
    assert "authentication failed" in record.error_message.lower()
    assert SMTP_PASSWORD not in record.error_message


def test_transient_failure_is_retried(client, sender, smtp):
    smtp.fail_on, smtp.error, smtp.fail_times = "send", smtplib.SMTPServerDisconnected(), 1
    body = client.post(SEND, json=EMAIL, headers=sender).json()
    assert body["status"] == "SENT"
    assert body["attempts"] == 2


def test_retries_stop_at_preference_limit(client, sender, smtp):
    client.put("/api/v1/preferences", json={**PREFS_UPDATE, "max_send_retries": 1, "default_cc": [], "default_bcc": []}, headers=sender)
    smtp.fail_on, smtp.error = "connect", TimeoutError()
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.status_code == 502
    assert response.json()["error"]["details"]["attempts"] == 2


def test_permanent_failure_is_not_retried(client, sender, smtp):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, b"no")
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.json()["error"]["details"]["attempts"] == 1


def test_recipient_and_subject_validation(client, sender, smtp):
    for payload in [
        {**EMAIL, "recipient": "not-an-email"},
        {**EMAIL, "subject": "Hi\r\nBcc: attacker@example.com"},
        {**EMAIL, "subject": " "},
        {**EMAIL, "body": ""},
        {**EMAIL, "cc": ["bad"]},
        {**EMAIL, "format": "PDF"},
    ]:
        assert client.post(SEND, json=payload, headers=sender).status_code == 422, payload
    assert smtp.sent == []


def test_recipient_limit(client, sender, smtp):
    client.put("/api/v1/preferences", json={**PREFS_UPDATE, "max_recipients_per_email": 2, "default_cc": [], "default_bcc": []}, headers=sender)
    response = client.post(SEND, json={**EMAIL, "cc": ["a@example.com", "b@example.com"]}, headers=sender)
    assert response.status_code == 400
    assert smtp.sent == []


def test_daily_send_limit(client, sender, smtp):
    client.put("/api/v1/preferences", json={**PREFS_UPDATE, "daily_send_limit": 1, "default_cc": [], "default_bcc": []}, headers=sender)
    assert client.post(SEND, json=EMAIL, headers=sender).status_code == 200
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.status_code == 429
    assert len(smtp.sent) == 1


def test_send_requires_smtp_configuration(client, auth_headers, smtp):
    create_company(client, auth_headers)
    response = client.post(SEND, json=EMAIL, headers=auth_headers)
    assert response.status_code == 404
    assert "smtp" in response.json()["error"]["message"].lower()


def test_each_company_sends_through_its_own_smtp_account(client, sender, other_auth_headers, smtp):
    create_company(client, other_auth_headers, XYZ_PROFILE)
    create_config(client, other_auth_headers, {**XYZ_SMTP, "password": "xyz-app-password", "sender_name": "Rahul"})

    client.post(SEND, json=EMAIL, headers=sender)
    client.post(SEND, json=EMAIL, headers=other_auth_headers)

    a, b = smtp.connections
    assert (a.host, a.logged_in_as, a.password_used) == ("smtp.abctech.com", "anjali@abctech.com", SMTP_PASSWORD)
    assert (b.host, b.logged_in_as, b.password_used) == ("smtp.xyzcorp.com", "rahul", "xyz-app-password")
    assert "anjali@abctech.com" in smtp.sent[0]["From"]
    assert smtp.sent[1]["From"] == "Rahul <rahul@xyzcorp.com>"


def test_ssl_mode_used_for_sending(client, sender, smtp):
    client.put("/api/v1/email-config", json={**SMTP_SETTINGS, "security_type": "SSL_TLS", "smtp_port": 465}, headers=sender)
    client.post(SEND, json=EMAIL, headers=sender)
    assert smtp.last.ssl is True
