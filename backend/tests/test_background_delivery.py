"""Background (Celery) email delivery: queueing, status transitions, retries, duplicates, isolation.

Celery runs eagerly in-process (no Redis); SMTP is the fake server from tests/fakes.py.
"""

import logging
import smtplib
import uuid

import pytest

from app.core.config import settings
from app.models import EmailAccount, EmailHistory, EmailStatus
from app.services.email_delivery import AttemptResult, attempt_delivery, retry_delay_seconds
from app.worker.celery_app import celery_app
from app.worker.tasks import send_email_task
from tests.fakes import install_fake_smtp
from tests.test_company import create_company
from tests.test_email_config import SMTP_PASSWORD, create_config
from tests.test_isolation import XYZ_PROFILE, XYZ_SMTP

SEND = "/api/v1/emails/send"
EMAIL = {"recipient": "priya@example.com", "subject": "Hello", "body": "Hi Priya,\n\nHello."}


@pytest.fixture()
def smtp(monkeypatch):
    return install_fake_smtp(monkeypatch)


@pytest.fixture()
def sender(client, auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    return auth_headers


def _record(db_session, history_id) -> EmailHistory:
    db_session.expire_all()
    return db_session.get(EmailHistory, uuid.UUID(history_id))


def _prefs(client, headers, **overrides):
    body = {
        "sender_name": None, "reply_to": None, "default_format": "PLAIN_TEXT", "daily_send_limit": 100,
        "max_recipients_per_email": 10, "max_send_retries": 2, "default_cc": [], "default_bcc": [], "extra_settings": {},
    }
    body.update(overrides)
    assert client.put("/api/v1/preferences", json=body, headers=headers).status_code == 200


# ----- queueing -------------------------------------------------------------------------------


def test_background_mode_returns_202_queued_and_worker_sends(client, sender, smtp, celery_eager, db_session):
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["task_id"]
    assert "queued" in body["message"].lower()
    # The eager worker already ran: exactly one message went through the company's SMTP account.
    assert len(smtp.sent) == 1
    record = _record(db_session, body["id"])
    assert record.status == EmailStatus.SENT and record.attempts == 1
    assert record.task_id == body["task_id"] and record.sent_at is not None
    assert smtp.last.host == "smtp.abctech.com" and smtp.last.password_used == SMTP_PASSWORD


def test_history_api_reports_status_for_polling(client, sender, smtp, celery_eager):
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    item = client.get(f"/api/v1/emails/history/{history_id}", headers=sender).json()
    assert item["status"] == "SENT" and item["attempts"] == 1 and item["last_attempt_at"]
    assert item["error_code"] is None


def test_sync_mode_is_unchanged(client, sender, smtp):
    assert settings.EMAIL_DELIVERY_MODE == "sync"
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.status_code == 200 and response.json()["status"] == "SENT"
    assert response.json()["task_id"] is None


def test_queue_unavailable_records_failure_and_returns_503(client, sender, smtp, monkeypatch, db_session):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "celery")

    def broken(*args, **kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.services.email_sender.enqueue_delivery", broken)
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["details"]["error_code"] == "queue_unavailable"
    assert "redis down" not in response.text
    record = _record(db_session, error["details"]["history_id"])
    assert record.status == EmailStatus.FAILED and record.error_code == "queue_unavailable"
    assert smtp.sent == []


# ----- status transitions & retries ----------------------------------------------------------------


def _queued(client, headers, monkeypatch) -> str:
    """Create a QUEUED history row without delivering it (enqueue is a no-op)."""
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "celery")
    monkeypatch.setattr("app.services.email_sender.enqueue_delivery", lambda history_id: "test-task-id")
    response = client.post(SEND, json=EMAIL, headers=headers)
    assert response.status_code == 202
    return response.json()["id"]


def test_transitions_queued_retrying_then_sent(client, sender, smtp, monkeypatch, db_session):
    history_id = _queued(client, sender, monkeypatch)
    assert _record(db_session, history_id).status == EmailStatus.QUEUED

    smtp.fail_on, smtp.error, smtp.fail_times = "send", smtplib.SMTPServerDisconnected(), 1
    first = attempt_delivery(db_session, uuid.UUID(history_id))
    assert first.result == AttemptResult.RETRY
    record = _record(db_session, history_id)
    assert record.status == EmailStatus.RETRYING and record.attempts == 1 and record.error_code == "disconnected"

    second = attempt_delivery(db_session, uuid.UUID(history_id))
    assert second.result == AttemptResult.SENT
    record = _record(db_session, history_id)
    assert record.status == EmailStatus.SENT and record.attempts == 2
    assert record.error_code is None and record.error_message is None


def test_worker_retries_transient_errors_then_succeeds(client, sender, smtp, celery_eager, db_session):
    smtp.fail_on, smtp.error, smtp.fail_times = "connect", TimeoutError(), 2
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    record = _record(db_session, history_id)
    assert record.status == EmailStatus.SENT and record.attempts == 3
    assert len(smtp.sent) == 1


def test_worker_stops_after_max_retries(client, sender, smtp, celery_eager, db_session):
    _prefs(client, sender, max_send_retries=1)
    smtp.fail_on, smtp.error = "connect", TimeoutError()
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    record = _record(db_session, history_id)
    assert record.status == EmailStatus.FAILED
    assert record.attempts == 2  # first attempt + 1 retry
    assert record.error_code == "timeout"
    assert smtp.sent == []


def test_permanent_errors_are_not_retried(client, sender, smtp, celery_eager, db_session):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, SMTP_PASSWORD.encode())
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    record = _record(db_session, history_id)
    assert record.status == EmailStatus.FAILED and record.attempts == 1
    assert record.error_code == "auth_failed"
    assert SMTP_PASSWORD not in (record.error_message or "")
    assert len(smtp.connections) == 1


def test_recipient_rejection_is_permanent(client, sender, smtp, celery_eager, db_session):
    smtp.fail_on = "send"
    smtp.error = smtplib.SMTPRecipientsRefused({"priya@example.com": (550, b"no such user")})
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    record = _record(db_session, history_id)
    assert record.status == EmailStatus.FAILED and record.error_code == "recipient_refused" and record.attempts == 1


def test_retry_delay_is_exponential_capped_and_jittered(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_RETRY_BASE_SECONDS", 30.0)
    monkeypatch.setattr(settings, "EMAIL_RETRY_MAX_SECONDS", 900.0)
    for attempts, expected in [(1, 30), (2, 60), (3, 120), (10, 900)]:
        delay = retry_delay_seconds(attempts)
        assert expected * 0.9 <= delay <= expected * 1.1, (attempts, delay)


# ----- duplicate prevention --------------------------------------------------------------------


def test_redelivered_task_does_not_send_twice(client, sender, smtp, celery_eager, db_session):
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    assert len(smtp.sent) == 1
    # The broker re-delivers the same message (e.g. after a worker restart).
    assert send_email_task.apply(args=[history_id]).get() == "skipped"
    assert send_email_task.apply(args=[history_id]).get() == "skipped"
    assert len(smtp.sent) == 1
    assert _record(db_session, history_id).attempts == 1


def test_task_skips_row_already_being_sent_by_another_worker(client, sender, smtp, monkeypatch, db_session):
    history_id = _queued(client, sender, monkeypatch)
    record = _record(db_session, history_id)
    record.status = EmailStatus.SENDING  # another worker claimed it
    db_session.commit()
    assert attempt_delivery(db_session, uuid.UUID(history_id)).result == AttemptResult.SKIPPED
    assert smtp.sent == []


def test_unknown_history_id_is_skipped(smtp, db_session):
    assert attempt_delivery(db_session, uuid.uuid4()).result == AttemptResult.SKIPPED


# ----- account problems at delivery time ------------------------------------------------------------


def test_account_deleted_before_delivery_fails_safely(client, sender, smtp, monkeypatch, db_session):
    history_id = _queued(client, sender, monkeypatch)
    account = db_session.query(EmailAccount).one()
    db_session.delete(account)
    db_session.commit()
    outcome = attempt_delivery(db_session, uuid.UUID(history_id))
    assert outcome.result == AttemptResult.FAILED
    record = _record(db_session, history_id)
    assert record.status == EmailStatus.FAILED and record.error_code == "account_unavailable"
    assert record.sender_email == "anjali@abctech.com"  # history keeps who it was from
    assert smtp.sent == []


def test_account_deactivated_before_delivery_fails_safely(client, sender, smtp, monkeypatch, db_session):
    history_id = _queued(client, sender, monkeypatch)
    account = db_session.query(EmailAccount).one()
    account.is_active = False
    db_session.commit()
    assert attempt_delivery(db_session, uuid.UUID(history_id)).result == AttemptResult.FAILED
    assert _record(db_session, history_id).error_code == "account_inactive"


def test_worker_never_uses_another_companys_account(client, sender, other_auth_headers, smtp, monkeypatch, db_session):
    history_id = _queued(client, sender, monkeypatch)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    create_config(client, other_auth_headers, XYZ_SMTP)
    foreign = db_session.query(EmailAccount).filter_by(email_address="rahul@xyzcorp.com").one()
    record = _record(db_session, history_id)
    record.email_account_id = foreign.id  # simulate a tampered/corrupted row
    db_session.commit()
    assert attempt_delivery(db_session, uuid.UUID(history_id)).result == AttemptResult.FAILED
    assert _record(db_session, history_id).error_code == "account_unavailable"
    assert smtp.sent == []


# ----- isolation, limits, secrets --------------------------------------------------------------------


def test_background_history_is_company_scoped(client, sender, other_auth_headers, smtp, celery_eager):
    history_id = client.post(SEND, json=EMAIL, headers=sender).json()["id"]
    create_company(client, other_auth_headers, XYZ_PROFILE)
    assert client.get(f"/api/v1/emails/history/{history_id}", headers=other_auth_headers).status_code == 404
    assert client.get("/api/v1/emails/history", headers=other_auth_headers).json()["total"] == 0


def test_queued_emails_count_toward_daily_limit(client, sender, smtp, monkeypatch):
    _prefs(client, sender, daily_send_limit=2)
    _queued(client, sender, monkeypatch)
    _queued(client, sender, monkeypatch)
    response = client.post(SEND, json=EMAIL, headers=sender)
    assert response.status_code == 429


def test_background_failure_logs_contain_no_secrets(client, sender, smtp, celery_eager, caplog):
    smtp.fail_on, smtp.error = "login", smtplib.SMTPAuthenticationError(535, SMTP_PASSWORD.encode())
    with caplog.at_level(logging.DEBUG):
        client.post(SEND, json=EMAIL, headers=sender)
    assert "auth_failed" in caplog.text
    assert SMTP_PASSWORD not in caplog.text


def test_celery_configuration():
    assert "email.send" in celery_app.tasks
    assert celery_app.conf.task_default_queue == "email"
    assert celery_app.conf.task_acks_late is False
    assert celery_app.conf.task_serializer == "json" and celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.broker_url == "memory://"  # tests never talk to a real Redis
