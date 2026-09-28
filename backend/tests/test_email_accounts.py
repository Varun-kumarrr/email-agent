"""Multiple email accounts per company: CRUD, defaults, isolation, secrets, sending."""

import uuid

import pytest

from app.core.encryption import decrypt_secret
from app.models import EmailAccount, EmailHistory
from tests.fakes import install_fake_smtp
from tests.test_company import create_company
from tests.test_isolation import XYZ_PROFILE

ACCOUNTS = "/api/v1/email-accounts"
GMAIL_APP_PASSWORD = "gmail-app-password-never-returned"
GENERIC_PASSWORD = "generic-smtp-password-never-returned"

GMAIL = {
    "account_name": "Gmail sales",
    "provider": "GMAIL",
    "email_address": "Sales@ABCTech.com",
    "sender_name": "ABC Sales",
    "reply_to": "replies@abctech.com",
    "password": GMAIL_APP_PASSWORD,
}
GENERIC = {
    "account_name": "Support (Zoho)",
    "provider": "GENERIC",
    "email_address": "support@abctech.com",
    "sender_name": "ABC Support",
    "smtp_host": "smtp.zoho.com",
    "smtp_port": 465,
    "security_type": "SSL_TLS",
    "smtp_username": "support@abctech.com",
    "password": GENERIC_PASSWORD,
}


@pytest.fixture()
def company(client, auth_headers):
    create_company(client, auth_headers)
    return auth_headers


def add(client, headers, payload):
    response = client.post(ACCOUNTS, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ----- CRUD & presets ---------------------------------------------------------------


def test_create_gmail_account_uses_smtp_preset(client, company):
    body = add(client, company, GMAIL)
    assert (body["smtp_host"], body["smtp_port"], body["security_type"]) == ("smtp.gmail.com", 587, "STARTTLS")
    assert body["provider"] == "GMAIL" and body["account_type"] == "SMTP"
    assert body["email_address"] == "sales@abctech.com"  # normalized
    assert body["smtp_username"] == "sales@abctech.com"  # defaults to the address
    assert body["password_configured"] is True and body["oauth_connected"] is False
    assert body["is_default"] is True and body["is_active"] is True  # first account becomes default


def test_create_generic_account_requires_connection_settings(client, company):
    missing = {k: v for k, v in GENERIC.items() if k not in ("smtp_host", "smtp_port", "security_type")}
    response = client.post(ACCOUNTS, json=missing, headers=company)
    assert response.status_code == 422
    assert GENERIC_PASSWORD not in response.text


def test_list_get_update_delete(client, company):
    first = add(client, company, GMAIL)
    second = add(client, company, GENERIC)
    listed = client.get(ACCOUNTS, headers=company).json()
    assert [a["id"] for a in listed] == [first["id"], second["id"]]  # default first

    fetched = client.get(f"{ACCOUNTS}/{second['id']}", headers=company).json()
    assert fetched["smtp_host"] == "smtp.zoho.com"

    patched = client.patch(
        f"{ACCOUNTS}/{second['id']}", json={"sender_name": "ABC Help Desk", "reply_to": None}, headers=company
    ).json()
    assert patched["sender_name"] == "ABC Help Desk" and patched["reply_to"] is None
    assert patched["smtp_host"] == "smtp.zoho.com"  # untouched

    assert client.delete(f"{ACCOUNTS}/{second['id']}", headers=company).status_code == 204
    assert client.get(f"{ACCOUNTS}/{second['id']}", headers=company).status_code == 404
    assert len(client.get(ACCOUNTS, headers=company).json()) == 1


def test_validation(client, company):
    for payload in [
        {**GENERIC, "email_address": "not-an-email"},
        {**GENERIC, "smtp_host": "http://smtp.zoho.com"},
        {**GENERIC, "smtp_port": 0},
        {**GENERIC, "security_type": "TLS1"},
        {**GENERIC, "provider": "YAHOO"},
        {**GENERIC, "password": ""},
        {k: v for k, v in GENERIC.items() if k != "password"},
        {**GENERIC, "account_name": " "},
    ]:
        assert client.post(ACCOUNTS, json=payload, headers=company).status_code == 422, payload


def test_duplicate_address_is_conflict(client, company):
    add(client, company, GMAIL)
    response = client.post(ACCOUNTS, json={**GMAIL, "email_address": "SALES@abctech.com"}, headers=company)
    assert response.status_code == 409


def test_unknown_account_is_404(client, company):
    missing = uuid.uuid4()
    assert client.get(f"{ACCOUNTS}/{missing}", headers=company).status_code == 404
    assert client.patch(f"{ACCOUNTS}/{missing}", json={"account_name": "x"}, headers=company).status_code == 404
    assert client.delete(f"{ACCOUNTS}/{missing}", headers=company).status_code == 404


def test_null_for_required_field_rejected(client, company):
    account = add(client, company, GENERIC)
    response = client.patch(f"{ACCOUNTS}/{account['id']}", json={"smtp_host": None}, headers=company)
    assert response.status_code == 400


# ----- default account rules ----------------------------------------------------------


def test_set_default_moves_the_flag(client, company):
    first = add(client, company, GMAIL)
    second = add(client, company, GENERIC)
    assert second["is_default"] is False
    body = client.post(f"{ACCOUNTS}/{second['id']}/set-default", headers=company).json()
    assert body["is_default"] is True
    defaults = [a["id"] for a in client.get(ACCOUNTS, headers=company).json() if a["is_default"]]
    assert defaults == [second["id"]]
    assert client.get(f"{ACCOUNTS}/{first['id']}", headers=company).json()["is_default"] is False


def test_create_with_is_default_takes_over(client, company):
    add(client, company, GMAIL)
    second = add(client, company, {**GENERIC, "is_default": True})
    defaults = [a["id"] for a in client.get(ACCOUNTS, headers=company).json() if a["is_default"]]
    assert defaults == [second["id"]]


def test_deactivating_default_promotes_next_active_account(client, company):
    first = add(client, company, GMAIL)
    second = add(client, company, GENERIC)
    body = client.patch(f"{ACCOUNTS}/{first['id']}", json={"is_active": False}, headers=company).json()
    assert body["is_active"] is False and body["is_default"] is False
    assert client.get(f"{ACCOUNTS}/{second['id']}", headers=company).json()["is_default"] is True


def test_deleting_default_promotes_next_account(client, company):
    first = add(client, company, GMAIL)
    second = add(client, company, GENERIC)
    client.delete(f"{ACCOUNTS}/{first['id']}", headers=company)
    assert client.get(f"{ACCOUNTS}/{second['id']}", headers=company).json()["is_default"] is True


def test_inactive_account_cannot_become_default(client, company):
    add(client, company, GMAIL)
    inactive = add(client, company, {**GENERIC, "is_active": False})
    assert inactive["is_default"] is False
    assert client.post(f"{ACCOUNTS}/{inactive['id']}/set-default", headers=company).status_code == 400
    assert client.post(ACCOUNTS, json={**GENERIC, "email_address": "x@abctech.com", "is_active": False, "is_default": True}, headers=company).status_code == 400


def test_reactivating_when_no_default_makes_it_default(client, company):
    only = add(client, company, GMAIL)
    client.patch(f"{ACCOUNTS}/{only['id']}", json={"is_active": False}, headers=company)
    body = client.patch(f"{ACCOUNTS}/{only['id']}", json={"is_active": True}, headers=company).json()
    assert body["is_default"] is True


# ----- secrets -------------------------------------------------------------------------


def test_passwords_are_encrypted_and_never_returned(client, company, db_session):
    gmail = client.post(ACCOUNTS, json=GMAIL, headers=company)
    generic = client.post(ACCOUNTS, json=GENERIC, headers=company)
    listing = client.get(ACCOUNTS, headers=company)
    for response in (gmail, generic, listing):
        assert GMAIL_APP_PASSWORD not in response.text and GENERIC_PASSWORD not in response.text
        assert "encrypted" not in response.text and "token" not in response.text.replace("oauth_token_expires_at", "")
    stored = db_session.query(EmailAccount).filter_by(email_address="sales@abctech.com").one()
    assert stored.encrypted_smtp_password != GMAIL_APP_PASSWORD
    assert decrypt_secret(stored.encrypted_smtp_password) == GMAIL_APP_PASSWORD


def test_patch_password_replaces_only_when_given(client, company, db_session):
    account = add(client, company, GENERIC)
    client.patch(f"{ACCOUNTS}/{account['id']}", json={"account_name": "Renamed"}, headers=company)
    stored = db_session.get(EmailAccount, uuid.UUID(account["id"]))
    db_session.refresh(stored)
    assert decrypt_secret(stored.encrypted_smtp_password) == GENERIC_PASSWORD
    response = client.patch(f"{ACCOUNTS}/{account['id']}", json={"password": "rotated-password"}, headers=company)
    assert "rotated-password" not in response.text
    db_session.refresh(stored)
    assert decrypt_secret(stored.encrypted_smtp_password) == "rotated-password"


def test_connection_change_resets_last_test(client, company, monkeypatch):
    install_fake_smtp(monkeypatch)
    account = add(client, company, GENERIC)
    client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "c@example.com"}, headers=company)
    assert client.get(f"{ACCOUNTS}/{account['id']}", headers=company).json()["last_test_success"] is True
    client.patch(f"{ACCOUNTS}/{account['id']}", json={"smtp_port": 587, "security_type": "STARTTLS"}, headers=company)
    assert client.get(f"{ACCOUNTS}/{account['id']}", headers=company).json()["last_test_success"] is None


# ----- isolation -----------------------------------------------------------------------


def test_accounts_are_isolated_between_companies(client, company, other_auth_headers):
    mine = add(client, company, GMAIL)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    assert client.get(ACCOUNTS, headers=other_auth_headers).json() == []
    url = f"{ACCOUNTS}/{mine['id']}"
    assert client.get(url, headers=other_auth_headers).status_code == 404
    assert client.patch(url, json={"account_name": "stolen"}, headers=other_auth_headers).status_code == 404
    assert client.delete(url, headers=other_auth_headers).status_code == 404
    assert client.post(f"{url}/set-default", headers=other_auth_headers).status_code == 404
    assert client.post(f"{url}/test", json={"recipient": "c@example.com"}, headers=other_auth_headers).status_code == 404
    assert client.get(url, headers=company).json()["account_name"] == "Gmail sales"


def test_accounts_require_auth_and_company(client, auth_headers):
    assert client.get(ACCOUNTS).status_code == 401
    assert client.get(ACCOUNTS, headers=auth_headers).status_code == 404  # no company yet


# ----- test email ----------------------------------------------------------------------


def test_account_test_uses_that_accounts_smtp_settings(client, company, monkeypatch):
    smtp = install_fake_smtp(monkeypatch)
    add(client, company, GMAIL)
    generic = add(client, company, GENERIC)
    result = client.post(f"{ACCOUNTS}/{generic['id']}/test", json={"recipient": "c@example.com"}, headers=company)
    assert result.json()["success"] is True
    assert (smtp.last.host, smtp.last.port, smtp.last.ssl) == ("smtp.zoho.com", 465, True)
    assert smtp.last.password_used == GENERIC_PASSWORD
    assert GENERIC_PASSWORD not in result.text


# ----- sending with a chosen account ------------------------------------------------------


EMAIL = {"recipient": "priya@example.com", "subject": "Hello", "body": "Hi Priya,\n\nHello."}


def test_send_uses_explicitly_selected_account(client, company, monkeypatch, db_session):
    smtp = install_fake_smtp(monkeypatch)
    add(client, company, GMAIL)
    generic = add(client, company, GENERIC)
    body = client.post("/api/v1/emails/send", json={**EMAIL, "email_account_id": generic["id"]}, headers=company).json()
    assert body["email_account_id"] == generic["id"]
    assert body["sender_email"] == "support@abctech.com"
    assert smtp.last.host == "smtp.zoho.com"
    assert smtp.sent[-1]["From"] == "ABC Support <support@abctech.com>"
    record = db_session.query(EmailHistory).one()
    assert str(record.email_account_id) == generic["id"]


def test_send_without_account_uses_default(client, company, monkeypatch):
    smtp = install_fake_smtp(monkeypatch)
    gmail = add(client, company, GMAIL)
    add(client, company, GENERIC)
    body = client.post("/api/v1/emails/send", json=EMAIL, headers=company).json()
    assert body["email_account_id"] == gmail["id"]
    assert smtp.last.host == "smtp.gmail.com"
    history = client.get("/api/v1/emails/history", headers=company).json()["items"][0]
    assert history["email_account_id"] == gmail["id"]


def test_send_with_inactive_account_rejected(client, company, monkeypatch):
    smtp = install_fake_smtp(monkeypatch)
    add(client, company, GMAIL)
    inactive = add(client, company, {**GENERIC, "is_active": False})
    response = client.post("/api/v1/emails/send", json={**EMAIL, "email_account_id": inactive["id"]}, headers=company)
    assert response.status_code == 400
    assert smtp.sent == []


def test_cannot_send_with_another_companys_account(client, company, other_auth_headers, monkeypatch):
    smtp = install_fake_smtp(monkeypatch)
    victim = add(client, company, GMAIL)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    response = client.post(
        "/api/v1/emails/send", json={**EMAIL, "email_account_id": victim["id"]}, headers=other_auth_headers
    )
    assert response.status_code == 404
    assert smtp.connections == []


def test_cannot_generate_with_another_companys_account(client, company, other_auth_headers):
    victim = add(client, company, GMAIL)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    response = client.post(
        "/api/v1/agent/generate-email",
        json={"recipient_name": "P", "recipient_email": "p@example.com", "purpose": "Intro", "email_account_id": victim["id"]},
        headers=other_auth_headers,
    )
    assert response.status_code == 404


def test_agent_uses_selected_accounts_sender_identity(client, company):
    add(client, company, GMAIL)
    generic = add(client, company, GENERIC)
    from app.core.dependencies import get_llm
    from app.main import app
    from tests.fakes import RecordingLLM

    llm = RecordingLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    try:
        client.post(
            "/api/v1/agent/generate-email",
            json={"recipient_name": "P", "recipient_email": "p@example.com", "purpose": "Intro", "email_account_id": generic["id"]},
            headers=company,
        )
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert "support@abctech.com" in llm.last.user_prompt and "ABC Support" in llm.last.user_prompt


def test_send_with_nonexistent_account_is_404_and_records_nothing(client, company, monkeypatch, db_session):
    smtp = install_fake_smtp(monkeypatch)
    add(client, company, GMAIL)
    response = client.post("/api/v1/emails/send", json={**EMAIL, "email_account_id": str(uuid.uuid4())}, headers=company)
    assert response.status_code == 404
    assert smtp.connections == []
    assert db_session.query(EmailHistory).count() == 0


def test_send_with_malformed_account_id_is_422(client, company, monkeypatch):
    smtp = install_fake_smtp(monkeypatch)
    add(client, company, GMAIL)
    response = client.post("/api/v1/emails/send", json={**EMAIL, "email_account_id": "not-a-uuid"}, headers=company)
    assert response.status_code == 422
    assert smtp.connections == []


def test_cannot_queue_with_another_companys_account(client, company, other_auth_headers, monkeypatch, celery_eager, db_session):
    """Background mode: the ownership check happens before anything is recorded or queued."""
    smtp = install_fake_smtp(monkeypatch)
    victim = add(client, company, GMAIL)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    add(client, other_auth_headers, {**GENERIC, "email_address": "info@xyzcorp.com"})
    response = client.post(
        "/api/v1/emails/send", json={**EMAIL, "email_account_id": victim["id"]}, headers=other_auth_headers
    )
    assert response.status_code == 404
    assert smtp.connections == []
    assert db_session.query(EmailHistory).count() == 0


def test_selected_account_in_background_mode_is_the_one_recorded_and_used(client, company, monkeypatch, celery_eager, db_session):
    smtp = install_fake_smtp(monkeypatch)
    add(client, company, GMAIL)  # default
    generic = add(client, company, GENERIC)
    response = client.post("/api/v1/emails/send", json={**EMAIL, "email_account_id": generic["id"]}, headers=company)
    assert response.status_code == 202
    assert response.json()["email_account_id"] == generic["id"]
    record = db_session.query(EmailHistory).one()
    db_session.refresh(record)
    assert str(record.email_account_id) == generic["id"] and record.status.value == "SENT"
    assert smtp.last.host == "smtp.zoho.com"


def test_send_with_no_account_is_404(client, company):
    response = client.post("/api/v1/emails/send", json=EMAIL, headers=company)
    assert response.status_code == 404


# ----- legacy /email-config compatibility -------------------------------------------------


def test_legacy_email_config_maps_to_primary_smtp_account(client, company):
    from tests.test_email_config import SMTP_SETTINGS

    assert client.post("/api/v1/email-config", json=SMTP_SETTINGS, headers=company).status_code == 201
    accounts = client.get(ACCOUNTS, headers=company).json()
    assert len(accounts) == 1 and accounts[0]["account_name"] == "Primary SMTP" and accounts[0]["is_default"]
    add(client, company, GMAIL)
    # The legacy API keeps showing the primary (default) SMTP account.
    assert client.get("/api/v1/email-config", headers=company).json()["email"] == "anjali@abctech.com"
    # ...and still refuses a second single configuration.
    assert client.post("/api/v1/email-config", json=SMTP_SETTINGS, headers=company).status_code == 409
