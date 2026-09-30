"""Regression tests for the defects found by the final 0-100 audit (see FINAL_TEST_REPORT.md).

D1  line breaks in sender names / subjects (email headers)
D2  SMTP SSRF guard must require globally routable addresses (incl. 100.64.0.0/10)
D3  an unexpected delivery exception must never leave an email SENDING
D4  accurate log line when every LLM provider fails
D5  temporary connection failures are retried; permanent ones are not
D6  bounded publish when the broker is down
D7  /health reports the email queue in background mode
D8  only failed logins count toward the login rate limit
plus the two untested behaviours: unreadable stored password, deactivated user.
"""

import logging
import smtplib
import socket
import time
import uuid

import pytest

from app.core.config import settings
from app.models import EmailAccount, EmailHistory, User
from app.services import smtp_client
from app.services.smtp_client import SmtpSendError
from tests.conftest import DEFAULT_PASSWORD, register_and_login
from tests.fakes import install_fake_smtp
from tests.test_company import create_company

ACCOUNTS = "/api/v1/email-accounts"
SEND = "/api/v1/emails/send"
HISTORY = "/api/v1/emails/history"
LOGIN = "/api/v1/auth/login"
SMTP_PASSWORD = "regression-smtp-password-never-leaks"
ACCOUNT = {
    "account_name": "Main", "provider": "GENERIC", "email_address": "sales@abctech.com", "sender_name": "Varun Kumar",
    "smtp_host": "smtp.abctech.com", "smtp_port": 587, "security_type": "STARTTLS", "smtp_username": "sales@abctech.com",
    "password": SMTP_PASSWORD,
}
EMAIL = {"recipient": "priya@example.com", "subject": "Hello", "body": "Hi Priya"}
PREFS = {
    "sender_name": None, "reply_to": None, "default_format": "PLAIN_TEXT", "daily_send_limit": 50,
    "max_recipients_per_email": 5, "max_send_retries": 2, "default_cc": [], "default_bcc": [], "extra_settings": {},
}
LINE_BREAKS = ["Varun\nKumar", "Varun\rKumar", "Varun\r\nKumar", "Varun Kumar", "Varun\x0bKumar", "Varun\x85Kumar"]


@pytest.fixture()
def company(client, auth_headers):
    create_company(client, auth_headers)
    return auth_headers


@pytest.fixture()
def smtp(monkeypatch):
    return install_fake_smtp(monkeypatch)


def only_history(db_session):
    rows = db_session.query(EmailHistory).all()
    for row in rows:
        db_session.refresh(row)
    return rows


# ----- D1: single-line header fields ---------------------------------------------------------


def test_d1_plain_sender_name_accepted(client, company):
    assert client.post(ACCOUNTS, json=ACCOUNT, headers=company).status_code == 201


@pytest.mark.parametrize("name", LINE_BREAKS)
def test_d1_account_create_rejects_line_breaks(client, company, name):
    response = client.post(ACCOUNTS, json={**ACCOUNT, "sender_name": name}, headers=company)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "sender_name"


@pytest.mark.parametrize("name", LINE_BREAKS)
def test_d1_account_update_rejects_line_breaks(client, company, name):
    account = client.post(ACCOUNTS, json=ACCOUNT, headers=company).json()
    assert client.patch(f"{ACCOUNTS}/{account['id']}", json={"sender_name": name}, headers=company).status_code == 422
    assert client.get(f"{ACCOUNTS}/{account['id']}", headers=company).json()["sender_name"] == "Varun Kumar"


@pytest.mark.parametrize("name", LINE_BREAKS)
def test_d1_preferences_reject_line_breaks(client, company, name):
    assert client.put("/api/v1/preferences", json={**PREFS, "sender_name": name}, headers=company).status_code == 422
    assert client.put("/api/v1/preferences", json={**PREFS, "sender_name": "Varun Kumar"}, headers=company).status_code == 200


@pytest.mark.parametrize("name", LINE_BREAKS)
def test_d1_legacy_email_config_rejects_line_breaks(client, company, name):
    payload = {"email": "a@abctech.com", "smtp_host": "smtp.abctech.com", "smtp_port": 587, "username": "a@abctech.com",
               "password": SMTP_PASSWORD, "security_type": "STARTTLS", "sender_name": name}
    assert client.post("/api/v1/email-config", json=payload, headers=company).status_code == 422


@pytest.mark.parametrize("subject", ["Hi there", "Hi\x0bthere", "Hi\x1cthere", "Hi there"])
def test_d1_subjects_reject_every_line_boundary(client, company, smtp, subject):
    """Previously only CR/LF were checked; Python's email package rejects all splitlines() boundaries."""
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    assert client.post(SEND, json={**EMAIL, "subject": subject}, headers=company).status_code == 422
    template = {"name": "T", "subject_template": subject, "body_template": "Body"}
    assert client.post("/api/v1/email-templates", json=template, headers=company).status_code == 422
    assert smtp.sent == []


def test_d1_template_values_and_ai_subjects_are_flattened(client, company):
    from app.services.agent.output_guard import clean_subject
    from app.utils.template_render import render

    rendered, _ = render("Hi {{ name }}", {"name": "Priya Bcc: x@example.com"}, single_line=True)
    assert rendered.splitlines() == [rendered]
    cleaned = clean_subject("Offer for\x85you")
    assert cleaned.splitlines() == [cleaned] and cleaned == "Offer for you"


# ----- D2: SSRF guard ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "10.0.0.1", "10.255.255.254", "172.16.0.1", "172.31.255.254", "192.168.0.1",
     "169.254.169.254", "100.64.0.0", "100.64.0.1", "100.100.100.200", "100.127.255.255", "0.0.0.0", "224.0.0.1", "::1"],
)
def test_d2_non_global_destinations_rejected(monkeypatch, host):
    monkeypatch.setattr(settings, "SMTP_ALLOW_PRIVATE_HOSTS", False)
    with pytest.raises(SmtpSendError) as info:
        smtp_client.ensure_public_host(host, 587)
    assert info.value.code == "host_not_allowed"


@pytest.mark.parametrize("address", ["100.63.255.255", "100.128.0.1", "8.8.8.8", "142.250.4.108", "2001:4860:4860::8888"])
def test_d2_global_destinations_allowed(monkeypatch, address):
    """Addresses just outside 100.64.0.0/10 and ordinary public addresses stay allowed."""
    monkeypatch.setattr(settings, "SMTP_ALLOW_PRIVATE_HOSTS", False)
    smtp_client.ensure_public_host(address, 587)


def _resolve_to(monkeypatch, *addresses):
    family = lambda a: socket.AF_INET6 if ":" in a else socket.AF_INET  # noqa: E731
    monkeypatch.setattr(
        smtp_client.socket, "getaddrinfo",
        lambda host, port, **kw: [(family(a), socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses],
    )


def test_d2_public_smtp_host_name_allowed(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_ALLOW_PRIVATE_HOSTS", False)
    _resolve_to(monkeypatch, "142.250.4.108")  # what smtp.gmail.com resolves to (no network in tests)
    smtp_client.ensure_public_host("smtp.gmail.com", 587)


def test_d2_host_name_resolving_into_cgnat_rejected(monkeypatch):
    """A public-looking name that resolves (even partly) into 100.64.0.0/10 is refused."""
    monkeypatch.setattr(settings, "SMTP_ALLOW_PRIVATE_HOSTS", False)
    _resolve_to(monkeypatch, "142.250.4.108", "100.100.100.200")
    with pytest.raises(SmtpSendError) as info:
        smtp_client.ensure_public_host("mail.example.com", 587)
    assert info.value.code == "host_not_allowed"


def test_d2_send_to_cgnat_host_never_connects(client, company, smtp, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_ALLOW_PRIVATE_HOSTS", False)
    _resolve_to(monkeypatch, "100.100.100.200")
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    response = client.post(SEND, json=EMAIL, headers=company)
    assert response.status_code == 502 and response.json()["error"]["details"]["error_code"] == "host_not_allowed"
    assert smtp.connections == []


# ----- D3: never stuck in SENDING --------------------------------------------------------------


def _explode(*args, **kwargs):
    raise RuntimeError(f"internal detail {SMTP_PASSWORD}")


def test_d3_unexpected_exception_sync_mode(client, company, smtp, monkeypatch, db_session, caplog):
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    monkeypatch.setattr(smtp_client, "send_message", _explode)
    with caplog.at_level(logging.DEBUG):
        response = client.post(SEND, json=EMAIL, headers=company)
    assert response.status_code == 502
    assert response.json()["error"]["details"]["error_code"] == "unexpected_error"
    [row] = only_history(db_session)
    assert (row.status.value, row.error_code, row.attempts) == ("FAILED", "unexpected_error", 1)  # not retried
    assert SMTP_PASSWORD not in response.text and SMTP_PASSWORD not in caplog.text
    assert "unexpected RuntimeError during delivery" in caplog.text


def test_d3_unexpected_exception_background_mode(client, company, smtp, monkeypatch, db_session, celery_eager):
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    monkeypatch.setattr(smtp_client, "send_message", _explode)
    assert client.post(SEND, json=EMAIL, headers=company).status_code == 202
    [row] = only_history(db_session)
    assert row.status.value == "FAILED" and row.error_code == "unexpected_error"


def test_d3_legacy_bad_sender_name_fails_cleanly(client, company, smtp, db_session, celery_eager):
    """Data stored before the D1 validation existed must not strand an email in SENDING."""
    account = client.post(ACCOUNTS, json=ACCOUNT, headers=company).json()
    row = db_session.get(EmailAccount, uuid.UUID(account["id"]))
    row.sender_name = "Evil\r\nBcc: attacker@example.com"
    db_session.commit()
    assert client.post(SEND, json=EMAIL, headers=company).status_code == 202
    [history] = only_history(db_session)
    assert history.status.value == "FAILED" and history.error_code == "unexpected_error"
    assert all("attacker@example.com" not in str(e) for e in smtp.envelopes)


def test_d3_gmail_provider_exception_fails_cleanly(client, company, monkeypatch, db_session):
    from app.services import email_delivery
    from tests.fake_google import install_fake_google
    from tests.test_gmail_oauth import connect

    install_fake_google(monkeypatch)
    oauth = connect(client, company)
    monkeypatch.setattr(email_delivery, "send_via_gmail", lambda *a, **k: (_ for _ in ()).throw(KeyError("id")))
    response = client.post(SEND, json={**EMAIL, "email_account_id": oauth["id"]}, headers=company)
    assert response.status_code == 502
    [row] = only_history(db_session)
    assert row.status.value == "FAILED" and row.error_code == "unexpected_error"


def test_d3_account_test_action_never_500(client, company, smtp, monkeypatch, db_session):
    account = client.post(ACCOUNTS, json=ACCOUNT, headers=company).json()
    monkeypatch.setattr(smtp_client, "send_message", _explode)
    response = client.post(f"{ACCOUNTS}/{account['id']}/test", json={"recipient": "o@example.com"}, headers=company)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False and body["error_code"] == "unexpected_error" and SMTP_PASSWORD not in response.text
    [row] = only_history(db_session)
    assert row.is_test and row.status.value == "FAILED"


def test_d3_known_smtp_failure_and_success_unchanged(client, company, smtp, db_session):
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    assert client.post(SEND, json=EMAIL, headers=company).json()["status"] == "SENT"
    smtp.fail_on, smtp.error = "send", smtplib.SMTPRecipientsRefused({"priya@example.com": (550, b"no")})
    assert client.post(SEND, json={**EMAIL, "subject": "Two"}, headers=company).status_code == 502
    statuses = sorted((r.subject, r.status.value, r.error_code) for r in only_history(db_session))
    assert statuses == [("Hello", "SENT", None), ("Two", "FAILED", "recipient_refused")]


def test_unreadable_stored_password_fails_safely(client, company, smtp, db_session):
    account = client.post(ACCOUNTS, json=ACCOUNT, headers=company).json()
    row = db_session.get(EmailAccount, uuid.UUID(account["id"]))
    row.encrypted_smtp_password = "gAAAAA" + "not-a-valid-fernet-token" * 3
    db_session.commit()
    response = client.post(SEND, json=EMAIL, headers=company)
    assert response.status_code == 502
    assert response.json()["error"]["details"]["error_code"] == "credential_unreadable"
    assert SMTP_PASSWORD not in response.text and "Traceback" not in response.text
    [history] = only_history(db_session)
    assert (history.status.value, history.attempts) == ("FAILED", 1)
    assert smtp.connections == []
    assert client.get(f"{ACCOUNTS}/{account['id']}", headers=company).json()["password_configured"] is True


# ----- D5: retry of temporary connection failures ---------------------------------------------


@pytest.mark.parametrize(
    ("error", "code"),
    [(ConnectionRefusedError(111, "refused"), "connection_refused"), (socket.gaierror(-3, "temporary failure"), "invalid_host")],
)
def test_d5_temporary_outage_retries_then_sends(client, company, smtp, db_session, celery_eager, error, code):
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    smtp.fail_on, smtp.error, smtp.fail_times = "connect", error, 1  # down for one attempt, then back
    assert client.post(SEND, json=EMAIL, headers=company).status_code == 202
    [row] = only_history(db_session)
    assert (row.status.value, row.attempts, row.error_code) == ("SENT", 2, None)
    assert len(smtp.sent) == 1  # delivered exactly once


def test_d5_permanent_outage_fails_after_retry_limit(client, company, smtp, db_session, celery_eager):
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    client.put("/api/v1/preferences", json={**PREFS, "max_send_retries": 2}, headers=company)
    smtp.fail_on, smtp.error = "connect", ConnectionRefusedError(111, "refused")
    client.post(SEND, json=EMAIL, headers=company)
    [row] = only_history(db_session)
    assert (row.status.value, row.attempts, row.error_code) == ("FAILED", 3, "connection_refused")
    assert smtp.sent == []


def test_d5_sync_mode_uses_the_same_bounded_retries(client, company, smtp, db_session):
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    smtp.fail_on, smtp.error, smtp.fail_times = "connect", ConnectionRefusedError(111, "refused"), 1
    assert client.post(SEND, json=EMAIL, headers=company).json()["status"] == "SENT"
    [row] = only_history(db_session)
    assert row.attempts == 2


def test_d5_authentication_failure_is_not_retried(client, company, smtp, db_session, celery_eager):
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, b"bad credentials")
    client.post(SEND, json=EMAIL, headers=company)
    [row] = only_history(db_session)
    assert (row.status.value, row.attempts, row.error_code) == ("FAILED", 1, "auth_failed")


def test_d5_blocked_host_is_not_retried(client, company, smtp, db_session, monkeypatch, celery_eager):
    monkeypatch.setattr(settings, "SMTP_ALLOW_PRIVATE_HOSTS", False)
    _resolve_to(monkeypatch, "10.0.0.5")
    client.post(ACCOUNTS, json=ACCOUNT, headers=company)
    client.post(SEND, json=EMAIL, headers=company)
    [row] = only_history(db_session)
    assert (row.status.value, row.attempts, row.error_code) == ("FAILED", 1, "host_not_allowed")


# ----- D6: bounded publish ---------------------------------------------------------------------


def test_d6_publish_to_unreachable_broker_is_bounded():
    from app.worker.celery_app import celery_app

    assert celery_app.conf.broker_connection_timeout == 2
    assert celery_app.conf.task_publish_retry_policy["max_retries"] == 1
    # Read timeouts too: a hung Redis (accepts connections, never answers) must not block forever.
    options = celery_app.conf.broker_transport_options
    assert options["socket_connect_timeout"] == 2 and options["socket_timeout"] == 5


def test_d6_d7_hung_broker_does_not_block_health_check():
    """Found while verifying D7 in Docker: a paused Redis made /health hang for >120 s."""
    from app.worker.celery_app import broker_reachable

    hung = socket.socket()
    hung.bind(("127.0.0.1", 0))
    hung.listen(5)  # the kernel accepts connections; nothing ever reads or replies
    try:
        started = time.monotonic()
        assert broker_reachable(timeout=1.0, url=f"redis://127.0.0.1:{hung.getsockname()[1]}/0") is False
        assert time.monotonic() - started < 4
    finally:
        hung.close()


# ----- D7: /health and the email queue --------------------------------------------------------


def test_d7_sync_mode_health_unchanged(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


def test_d7_background_mode_reports_queue(client, monkeypatch):
    from app.worker import celery_app as worker

    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "celery")
    monkeypatch.setattr(worker, "broker_reachable", lambda timeout=1.0, url=None: True)
    response = client.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok", "database": "ok", "queue": "ok"}
    monkeypatch.setattr(worker, "broker_reachable", lambda timeout=1.0, url=None: False)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "ok", "queue": "unreachable"}


def test_d7_broker_check_is_real_and_bounded():
    from app.worker.celery_app import broker_reachable

    assert broker_reachable(url="memory://") is True
    started = time.monotonic()
    assert broker_reachable(timeout=1.0, url="redis://127.0.0.1:1/0") is False  # nothing listens on port 1
    assert time.monotonic() - started < 5


# ----- D8: login rate limit counts failures only -----------------------------------------------


def test_d8_successful_logins_do_not_consume_budget(client):
    register_and_login(client)
    for _ in range(15):
        assert client.post(LOGIN, json={"email": "anjali@abctech.com", "password": DEFAULT_PASSWORD}).status_code == 200


def test_d8_failed_logins_trigger_limit_even_for_correct_password(client):
    register_and_login(client)
    codes = [client.post(LOGIN, json={"email": "anjali@abctech.com", "password": "Wrong1234"}).status_code for _ in range(10)]
    assert codes == [401] * 10
    assert client.post(LOGIN, json={"email": "anjali@abctech.com", "password": DEFAULT_PASSWORD}).status_code == 429


def test_d8_mixed_attempts_only_failures_count(client):
    register_and_login(client)
    ok = {"email": "anjali@abctech.com", "password": DEFAULT_PASSWORD}
    bad = {"email": "anjali@abctech.com", "password": "Wrong1234"}
    for _ in range(9):
        client.post(LOGIN, json=bad)
        assert client.post(LOGIN, json=ok).status_code == 200  # interleaved successes are not counted
    assert client.post(LOGIN, json=bad).status_code == 401  # 10th failure
    assert client.post(LOGIN, json=ok).status_code == 429
    # The limit is per IP + account: another account from the same client is unaffected.
    assert client.post(LOGIN, json={"email": "other@example.com", "password": "Wrong1234"}).status_code == 401


# ----- D4: accurate log when every provider fails ---------------------------------------------


def test_d4_log_names_all_failed_providers(client, company, caplog):
    from app.core.dependencies import get_llm
    from app.main import app
    from app.services.llm import FallbackLLMProvider
    from tests.test_groq_provider import _failing, gemini, groq

    app.dependency_overrides[get_llm] = lambda: FallbackLLMProvider([groq(_failing(500)), gemini(_failing(503))])
    try:
        with caplog.at_level(logging.WARNING):
            body = client.post(
                "/api/v1/agent/generate-email",
                json={"recipient_name": "P", "recipient_email": "p@example.com", "purpose": "Intro"},
                headers=company,
            ).json()
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert body["provider"] == "mock"
    assert "LLM generation failed: all providers failed (groq, gemini)" in caplog.text


# ----- deactivated users ----------------------------------------------------------------------


def test_deactivated_user_loses_access_including_existing_tokens(client, db_session):
    headers = register_and_login(client, email="leaver@example.com", name="Leaver")
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    user = db_session.query(User).filter_by(email="leaver@example.com").one()
    user.is_active = False
    db_session.commit()
    for path in ("/api/v1/auth/me", "/api/v1/company", "/api/v1/email-accounts", HISTORY):
        assert client.get(path, headers=headers).status_code == 401
    assert client.post(LOGIN, json={"email": "leaver@example.com", "password": DEFAULT_PASSWORD}).status_code == 401
