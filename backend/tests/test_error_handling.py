import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.error_handlers import register_exception_handlers
from app.core.exceptions import ForbiddenError
from app.core.logging import RedactingFilter, redact


def _assert_error_shape(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code


def test_unknown_route_is_consistent_404(client):
    _assert_error_shape(client.get("/api/v1/does-not-exist"), 404, "not_found")


def test_wrong_method_is_consistent_405(client):
    _assert_error_shape(client.delete("/api/v1/auth/login"), 405, "method_not_allowed")


def test_validation_error_shape(client):
    response = client.post("/api/v1/auth/register", json={"email": "x"})
    _assert_error_shape(response, 422, "validation_error")
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert {"email", "password", "name"} <= fields


def test_malformed_json_is_422(client):
    response = client.post(
        "/api/v1/auth/login", content="{not json", headers={"Content-Type": "application/json"}
    )
    _assert_error_shape(response, 422, "validation_error")


@pytest.fixture()
def failing_client():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail: db password is hunter2")

    @app.get("/db-down")
    def db_down():
        raise OperationalError("SELECT 1", {}, Exception("connection to server failed: password=hunter2"))

    @app.get("/integrity")
    def integrity():
        raise IntegrityError("INSERT", {}, Exception("duplicate key value violates unique constraint"))

    @app.get("/forbidden")
    def forbidden():
        raise ForbiddenError()

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_returns_generic_500(failing_client):
    response = failing_client.get("/boom")
    _assert_error_shape(response, 500, "internal_error")
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


def test_database_unavailable_returns_503(failing_client):
    response = failing_client.get("/db-down")
    _assert_error_shape(response, 503, "database_unavailable")
    assert "hunter2" not in response.text


def test_integrity_error_returns_409(failing_client):
    response = failing_client.get("/integrity")
    _assert_error_shape(response, 409, "conflict")
    assert "unique constraint" not in response.text


def test_forbidden_returns_403(failing_client):
    _assert_error_shape(failing_client.get("/forbidden"), 403, "forbidden")


def test_redaction_of_secrets_in_logs():
    assert "abc.def" not in redact("Authorization: Bearer abc.def")
    assert "hunter2" not in redact("password=hunter2")
    assert "hunter2" not in redact("postgresql+psycopg://postgres:hunter2@localhost/db")
    assert "AIza" + "FAKE_KEY_FOR_REDACTION_TEST" not in redact("key AIza" + "FAKE_KEY_FOR_REDACTION_TEST")
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdefghijklmnop"
    assert jwt not in redact(f"token {jwt}")


def test_redacting_filter_rewrites_records():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "login with password=%s", ("hunter2",), None)
    RedactingFilter().filter(record)
    assert "hunter2" not in record.getMessage()
