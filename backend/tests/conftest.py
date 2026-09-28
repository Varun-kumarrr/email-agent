"""Shared test fixtures.

Tests run against an isolated in-memory SQLite database (schema built from the
models), so they never touch a real PostgreSQL database and need no credentials.
SMTP and the LLM are always mocked.
"""

import os

# Settings are read at import time, so configure the test environment first.
os.environ["SECRET_KEY"] = "test-secret-key-that-is-only-used-in-tests"
os.environ["ENCRYPTION_KEY"] = ""
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = ""
os.environ["SMTP_RETRY_BACKOFF_SECONDS"] = "0"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.database import get_db
from app.main import app


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture()
def client(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


DEFAULT_PASSWORD = "Str0ngPassw0rd"


def register_and_login(client, email="anjali@abctech.com", name="Anjali", password=DEFAULT_PASSWORD):
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "name": name}
    )
    assert response.status_code == 201, response.text
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def auth_headers(client):
    return register_and_login(client)


@pytest.fixture()
def other_auth_headers(client):
    return register_and_login(client, email="rahul@xyzcorp.com", name="Rahul")
