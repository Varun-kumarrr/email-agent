"""Shared test fixtures.

By default tests run against an isolated in-memory SQLite database (schema built
from the models), so they need no credentials and never touch the application
database. Set TEST_DATABASE_URL to a *separate* PostgreSQL database whose name
ends in "_test" to run the same suite against PostgreSQL:

    TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/email_agent_test pytest

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
from sqlalchemy import create_engine, event, make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.database import get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


def _checked_postgres_url(url: str) -> str:
    """Refuse anything that could be the real application database."""
    parsed = make_url(url)
    if not (parsed.database or "").endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must point to a database whose name ends with '_test'")
    if parsed.render_as_string(hide_password=False) == make_url(settings.DATABASE_URL).render_as_string(hide_password=False):
        raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL")
    return url


@pytest.fixture(scope="session")
def _postgres_engine():
    if not TEST_DATABASE_URL:
        yield None
        return
    engine = create_engine(_checked_postgres_url(TEST_DATABASE_URL), hide_parameters=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def engine(_postgres_engine):
    if _postgres_engine is not None:
        # Empty every table before each test (children first).
        with _postgres_engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        yield _postgres_engine
        return

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
