"""Gmail OAuth: state/CSRF, authorize, callback, token storage and refresh, Gmail API delivery.

Google is simulated by tests/fake_google.py; no test talks to Google.
Real Gmail OAuth delivery is verified manually with the user's own Google client.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.core.encryption import decrypt_secret
from app.core.logging import OAuthQueryRedactingFilter
from app.models import AccountType, EmailAccount, EmailHistory, EmailProvider, EmailStatus, OAuthState
from app.services.oauth_service import _hash_state
from tests.fake_google import install_fake_google
from tests.fakes import install_fake_smtp
from tests.test_company import create_company
from tests.test_isolation import XYZ_PROFILE

AUTHORIZE = "/api/v1/oauth/gmail/authorize"
CALLBACK = "/api/v1/oauth/gmail/callback"
ACCOUNTS = "/api/v1/email-accounts"
SEND = "/api/v1/emails/send"
CLIENT_SECRET = "test-client-secret-value"


@pytest.fixture()
def google(monkeypatch):
    return install_fake_google(monkeypatch)


@pytest.fixture()
def company(client, auth_headers):
    create_company(client, auth_headers)
    return auth_headers


def authorize(client, headers) -> tuple[str, dict]:
    response = client.get(AUTHORIZE, headers=headers)
    assert response.status_code == 200, response.text
    url = response.json()["authorization_url"]
    return url, {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def callback(client, **params):
    return client.get(CALLBACK, params=params, follow_redirects=False)


def redirect_params(response) -> dict:
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("http://localhost:3000/email-accounts?")
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


def connect(client, headers) -> dict:
    _, params = authorize(client, headers)
    result = redirect_params(callback(client, state=params["state"], code="fake-auth-code"))
    assert result == {"oauth": "gmail", "status": "success"}, result
    return next(a for a in client.get(ACCOUNTS, headers=headers).json() if a["account_type"] == "OAUTH")


# ----- authorize ---------------------------------------------------------------------------------


def test_authorize_returns_google_url_with_exact_parameters(client, company, google, db_session):
    url, params = authorize(client, company)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert params["client_id"] == "test-client-id.apps.googleusercontent.com"
    assert params["redirect_uri"] == "http://localhost:8000/api/v1/oauth/gmail/callback"
    assert params["scope"].split() == ["openid", "email", "https://www.googleapis.com/auth/gmail.send"]
    assert params["response_type"] == "code"
    assert params["access_type"] == "offline" and params["prompt"] == "consent"
    assert params["code_challenge_method"] == "S256" and len(params["code_challenge"]) == 43
    assert CLIENT_SECRET not in url  # the secret never goes to the browser
    # Only a hash of the state is stored; the verifier is encrypted.
    row = db_session.query(OAuthState).one()
    assert row.state_hash == _hash_state(params["state"]) and params["state"] not in row.state_hash
    assert row.provider == EmailProvider.GMAIL and row.consumed_at is None
    assert row.expires_at > datetime.now(timezone.utc)
    assert decrypt_secret(row.encrypted_code_verifier) != params["code_challenge"]


def test_state_is_random_and_carries_no_identifiers(client, company, google, db_session):
    _, first = authorize(client, company)
    _, second = authorize(client, company)
    assert first["state"] != second["state"] and len(first["state"]) >= 40
    row = db_session.query(OAuthState).first()
    for identifier in (str(row.user_id), str(row.company_id)):
        assert identifier not in first["state"]


def test_authorize_requires_authentication_and_company(client, auth_headers, google):
    assert client.get(AUTHORIZE).status_code == 401
    assert client.get(AUTHORIZE, headers=auth_headers).status_code == 404  # no company yet


def test_authorize_when_not_configured_is_503(client, company, monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", SecretStr(""))
    response = client.get(AUTHORIZE, headers=company)
    assert response.status_code == 503
    assert "not configured" in response.json()["error"]["message"]


# ----- callback: success ------------------------------------------------------------------------------


def test_callback_creates_encrypted_gmail_oauth_account(client, company, google, db_session):
    _, params = authorize(client, company)
    response = callback(client, state=params["state"], code="fake-auth-code")
    assert redirect_params(response) == {"oauth": "gmail", "status": "success"}
    for secret in ("fake-auth-code", "fake-access-token", "fake-refresh-token", CLIENT_SECRET):
        assert secret not in response.headers["location"] and secret not in response.text

    # The code was exchanged server-side with the PKCE verifier and the exact redirect URI.
    exchange = google.token_requests[-1]
    assert exchange["grant_type"] == "authorization_code" and exchange["code"] == "fake-auth-code"
    assert exchange["redirect_uri"] == settings.GOOGLE_REDIRECT_URI
    assert len(exchange["code_verifier"]) >= 43

    account = db_session.query(EmailAccount).one()
    assert (account.account_type, account.provider) == (AccountType.OAUTH, EmailProvider.GMAIL)
    assert account.email_address == "sales.abctech@gmail.com"
    assert account.encrypted_oauth_access_token != "fake-access-token-1"
    assert decrypt_secret(account.encrypted_oauth_access_token) == "fake-access-token-1"
    assert decrypt_secret(account.encrypted_oauth_refresh_token) == "fake-refresh-token"
    assert "gmail.send" in account.oauth_scopes
    assert account.oauth_token_expires_at > datetime.now(timezone.utc)
    assert account.smtp_host is None and account.encrypted_smtp_password is None
    assert account.is_default is True  # first account of the company

    listed = client.get(ACCOUNTS, headers=company)
    assert listed.json()[0]["oauth_connected"] is True
    for secret in ("fake-access-token", "fake-refresh-token", "encrypted"):
        assert secret not in listed.text


def test_reconnect_updates_tokens_without_duplicating(client, company, google, db_session):
    connect(client, company)
    google.issue_refresh_token = False  # Google may omit it on reconnect
    _, params = authorize(client, company)
    result = redirect_params(callback(client, state=params["state"], code="second-code"))
    assert result == {"oauth": "gmail", "status": "success", "reason": "reconnected"}
    account = db_session.query(EmailAccount).one()
    db_session.refresh(account)
    assert decrypt_secret(account.encrypted_oauth_access_token) == "fake-access-token-2"
    assert decrypt_secret(account.encrypted_oauth_refresh_token) == "fake-refresh-token"  # kept


def test_oauth_account_coexists_with_smtp_account_for_same_address(client, company, google):
    client.post(
        ACCOUNTS,
        json={"account_name": "Gmail SMTP", "provider": "GMAIL", "email_address": "sales.abctech@gmail.com",
              "sender_name": "ABC", "password": "abcd efgh ijkl mnop"},
        headers=company,
    )
    oauth = connect(client, company)
    accounts = client.get(ACCOUNTS, headers=company).json()
    assert len(accounts) == 2
    assert oauth["is_default"] is False  # the SMTP account was already the default
    assert [a["account_type"] for a in accounts if a["is_default"]] == ["SMTP"]


# ----- callback: state validation & errors ---------------------------------------------------------------


def test_state_is_single_use(client, company, google, db_session):
    _, params = authorize(client, company)
    assert redirect_params(callback(client, state=params["state"], code="c1"))["status"] == "success"
    replay = redirect_params(callback(client, state=params["state"], code="c1"))
    assert replay == {"oauth": "gmail", "status": "error", "reason": "state_used"}
    assert db_session.query(EmailAccount).count() == 1


def test_expired_state_is_rejected(client, company, google, db_session):
    _, params = authorize(client, company)
    row = db_session.query(OAuthState).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    result = redirect_params(callback(client, state=params["state"], code="c"))
    assert result["reason"] == "state_expired"
    assert google.token_requests == []  # never exchanged
    assert db_session.query(EmailAccount).count() == 0


@pytest.mark.parametrize(("state", "reason"), [(None, "state_missing"), ("forged-state-value", "state_invalid"), ("x" * 500, "state_invalid")])
def test_invalid_or_missing_state_is_rejected(client, company, google, state, reason):
    params = {"code": "c"} if state is None else {"state": state, "code": "c"}
    assert redirect_params(callback(client, **params))["reason"] == reason
    assert google.token_requests == []


def test_state_for_another_provider_is_rejected(client, company, google, db_session):
    _, params = authorize(client, company)
    row = db_session.query(OAuthState).one()
    row.provider = EmailProvider.OUTLOOK
    db_session.commit()
    assert redirect_params(callback(client, state=params["state"], code="c"))["reason"] == "state_invalid"


def test_user_cancelled_consent(client, company, google, db_session):
    _, params = authorize(client, company)
    result = redirect_params(callback(client, state=params["state"], error="access_denied"))
    assert result["reason"] == "access_denied"
    assert db_session.query(OAuthState).one().consumed_at is not None  # consumed even on error


def test_token_exchange_failure_is_safe(client, company, google, caplog):
    google.token_error = "invalid_grant"
    _, params = authorize(client, company)
    with caplog.at_level(logging.DEBUG):
        result = redirect_params(callback(client, state=params["state"], code="secret-auth-code"))
    assert result["reason"] == "token_exchange_failed"
    assert "secret-auth-code" not in caplog.text and CLIENT_SECRET not in caplog.text


def test_missing_gmail_send_scope_is_rejected(client, company, google, db_session):
    google.scope = "openid https://www.googleapis.com/auth/userinfo.email"  # user unticked "send email"
    _, params = authorize(client, company)
    assert redirect_params(callback(client, state=params["state"], code="c"))["reason"] == "scope_missing"
    assert db_session.query(EmailAccount).count() == 0


def test_unverified_email_is_rejected(client, company, google, db_session):
    google.email_verified = False
    _, params = authorize(client, company)
    assert redirect_params(callback(client, state=params["state"], code="c"))["reason"] == "email_unverified"
    assert db_session.query(EmailAccount).count() == 0


def test_new_account_without_refresh_token_is_rejected(client, company, google, db_session):
    google.issue_refresh_token = False
    _, params = authorize(client, company)
    assert redirect_params(callback(client, state=params["state"], code="c"))["reason"] == "refresh_token_missing"
    assert db_session.query(EmailAccount).count() == 0


def test_callback_redirect_is_fixed_not_user_controlled(client, company, google):
    _, params = authorize(client, company)
    response = client.get(
        CALLBACK, params={"state": params["state"], "code": "c", "redirect_uri": "https://evil.example.com"}, follow_redirects=False
    )
    assert response.headers["location"].startswith("http://localhost:3000/email-accounts?")
    assert response.headers["cache-control"] == "no-store"


# ----- isolation ---------------------------------------------------------------------------------------------


def test_connection_lands_in_the_company_that_started_it(client, company, other_auth_headers, google, db_session):
    create_company(client, other_auth_headers, XYZ_PROFILE)
    _, params = authorize(client, company)
    # The callback carries no JWT; the account goes to the company bound to the state.
    callback(client, state=params["state"], code="c")
    assert len(client.get(ACCOUNTS, headers=company).json()) == 1
    assert client.get(ACCOUNTS, headers=other_auth_headers).json() == []


def test_other_company_cannot_use_or_test_an_oauth_account(client, company, other_auth_headers, google):
    oauth = connect(client, company)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    assert client.post(f"{ACCOUNTS}/{oauth['id']}/test", json={"recipient": "o@example.com"}, headers=other_auth_headers).status_code == 404
    response = client.post(SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b", "email_account_id": oauth["id"]}, headers=other_auth_headers)
    assert response.status_code == 404
    assert google.sent == []


def test_oauth_account_smtp_fields_cannot_be_edited(client, company, google):
    oauth = connect(client, company)
    response = client.patch(f"{ACCOUNTS}/{oauth['id']}", json={"smtp_host": "smtp.evil.com"}, headers=company)
    assert response.status_code == 400
    renamed = client.patch(f"{ACCOUNTS}/{oauth['id']}", json={"sender_name": "ABC Sales"}, headers=company)
    assert renamed.status_code == 200 and renamed.json()["sender_name"] == "ABC Sales"


# ----- Gmail API delivery ---------------------------------------------------------------------------------------


def test_test_email_uses_gmail_api(client, company, google):
    oauth = connect(client, company)
    result = client.post(f"{ACCOUNTS}/{oauth['id']}/test", json={"recipient": "owner@example.com"}, headers=company).json()
    assert result["success"] is True
    sent = google.sent[-1]
    assert sent["auth"] == "Bearer fake-access-token-1"
    assert sent["message"]["To"] == "owner@example.com"
    assert "sales.abctech@gmail.com" in sent["message"]["From"]
    assert "fake-access-token" not in str(result)


def test_send_builds_full_mime_for_gmail_api(client, company, google, monkeypatch):
    smtp = install_fake_smtp(monkeypatch)
    oauth = connect(client, company)
    client.patch(f"{ACCOUNTS}/{oauth['id']}", json={"sender_name": "ABC Sales", "reply_to": "replies@abctech.com"}, headers=company)
    client.post(
        "/api/v1/signature",
        json={"signature_text": "Best Regards,\nAnjali\nABC Technologies", "enabled": True, "append_automatically": True},
        headers=company,
    )
    body = client.post(
        SEND,
        json={
            "recipient": "priya@example.com", "subject": "CRM demo", "body": "Hi Priya,\n\nShort note.\n\nBest regards,",
            "format": "HTML", "cc": ["cc@example.com"], "bcc": ["hidden@example.com"], "email_account_id": oauth["id"],
        },
        headers=company,
    ).json()
    assert body["status"] == "SENT" and body["email_account_id"] == oauth["id"]
    assert smtp.connections == []  # Gmail API, not SMTP
    raw, message = google.sent[-1]["raw"], google.sent[-1]["message"]
    assert b"\r\n" in raw  # RFC 5322 CRLF line endings
    assert message["From"] == "ABC Sales <sales.abctech@gmail.com>"
    assert message["To"] == "priya@example.com" and message["Cc"] == "cc@example.com"
    assert message["Bcc"] == "hidden@example.com"  # the Gmail API reads and then strips it
    assert message["Reply-To"] == "replies@abctech.com" and message["Subject"] == "CRM demo"
    text = message.get_body(preferencelist=("plain",)).get_content()
    html_part = message.get_body(preferencelist=("html",)).get_content()
    assert text.count("ABC Technologies") == 1 and "<p>Hi Priya,</p>" in html_part


def test_expired_access_token_is_refreshed_and_stored_encrypted(client, company, google, db_session):
    oauth = connect(client, company)
    account = db_session.get(EmailAccount, uuid.UUID(oauth["id"]))
    account.oauth_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    client.post(SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b", "email_account_id": oauth["id"]}, headers=company)
    assert google.token_requests[-1]["grant_type"] == "refresh_token"
    assert google.token_requests[-1]["refresh_token"] == "fake-refresh-token"
    assert google.sent[-1]["auth"] == "Bearer fake-access-token-2"
    db_session.refresh(account)
    assert decrypt_secret(account.encrypted_oauth_access_token) == "fake-access-token-2"
    assert account.oauth_token_expires_at > datetime.now(timezone.utc) + timedelta(minutes=30)


def test_valid_access_token_is_not_refreshed(client, company, google):
    oauth = connect(client, company)
    client.post(SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b", "email_account_id": oauth["id"]}, headers=company)
    assert [r["grant_type"] for r in google.token_requests] == ["authorization_code"]


def test_rejected_token_triggers_one_refresh_and_retry(client, company, google):
    oauth = connect(client, company)
    google.send_statuses = [401]  # revoked before its recorded expiry
    body = client.post(SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b", "email_account_id": oauth["id"]}, headers=company).json()
    assert body["status"] == "SENT"
    assert google.sent[-1]["auth"] == "Bearer fake-access-token-2"


def test_revoked_refresh_token_fails_permanently_with_reconnect_message(client, company, google, db_session):
    oauth = connect(client, company)
    account = db_session.get(EmailAccount, uuid.UUID(oauth["id"]))
    account.oauth_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()
    google.refresh_error = "invalid_grant"
    response = client.post(SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b", "email_account_id": oauth["id"]}, headers=company)
    assert response.status_code == 502
    details = response.json()["error"]
    assert details["details"]["error_code"] == "oauth_revoked" and details["details"]["attempts"] == 1
    assert "Reconnect Gmail" in details["message"]
    assert "fake-refresh-token" not in response.text


def test_gmail_rate_limit_is_retried_then_sent(client, company, google):
    oauth = connect(client, company)
    google.send_statuses = [429]
    body = client.post(SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b", "email_account_id": oauth["id"]}, headers=company).json()
    assert body["status"] == "SENT" and body["attempts"] == 2


def test_gmail_forbidden_is_permanent(client, company, google):
    oauth = connect(client, company)
    google.send_statuses = [403]
    response = client.post(SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b", "email_account_id": oauth["id"]}, headers=company)
    assert response.status_code == 502
    assert response.json()["error"]["details"]["error_code"] == "gmail_forbidden"
    assert response.json()["error"]["details"]["attempts"] == 1


def test_background_delivery_through_gmail_oauth(client, company, google, celery_eager, db_session):
    oauth = connect(client, company)
    response = client.post(SEND, json={"recipient": "p@example.com", "subject": "queued", "body": "b", "email_account_id": oauth["id"]}, headers=company)
    assert response.status_code == 202 and response.json()["status"] == "QUEUED"
    db_session.expire_all()
    record = db_session.get(EmailHistory, uuid.UUID(response.json()["id"]))
    assert record.status == EmailStatus.SENT and google.sent[-1]["message"]["Subject"] == "queued"


def test_default_gmail_oauth_account_is_used_when_none_selected(client, company, google):
    connect(client, company)
    body = client.post(SEND, json={"recipient": "p@example.com", "subject": "s", "body": "b"}, headers=company).json()
    assert body["sender_email"] == "sales.abctech@gmail.com" and len(google.sent) == 1


# ----- logging ------------------------------------------------------------------------------------------------


def test_access_log_filter_redacts_oauth_query_string():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", "/api/v1/oauth/gmail/callback?state=abc&code=4/0secret-code", "1.1", 302), None,
    )
    OAuthQueryRedactingFilter().filter(record)
    message = record.getMessage()
    assert "secret-code" not in message and "state=abc" not in message
    assert "/api/v1/oauth/gmail/callback?[redacted]" in message


def test_full_flow_logs_contain_no_tokens_or_codes(client, company, google, caplog):
    with caplog.at_level(logging.DEBUG):
        oauth = connect(client, company)
        client.post(f"{ACCOUNTS}/{oauth['id']}/test", json={"recipient": "o@example.com"}, headers=company)
    for secret in ("fake-auth-code", "fake-access-token", "fake-refresh-token", CLIENT_SECRET):
        assert secret not in caplog.text
