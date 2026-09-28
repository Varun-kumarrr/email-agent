"""Shared test fixtures.

Every test runs against a dedicated PostgreSQL test database (for example
`email_agent_test`), never the application database. Its URL comes from the
TEST_DATABASE_URL environment variable, or from the git-ignored backend/.env:

    TEST_DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/email_agent_test

The schema is created with the real Alembic migrations, and every table is
emptied before each test. SMTP and the LLM are always mocked.
"""

import os
from pathlib import Path

# Settings are read at import time, so configure the test environment first.
os.environ["SECRET_KEY"] = "test-secret-key-that-is-only-used-in-tests"
os.environ["ENCRYPTION_KEY"] = ""
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = ""
os.environ["SMTP_RETRY_BACKOFF_SECONDS"] = "0"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.config import settings
from app.core.rate_limit import ALL_LIMITERS
from app.db.base import Base
from app.db.database import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


class _TestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    TEST_DATABASE_URL: str = ""


def test_database_url() -> str:
    """The PostgreSQL test database URL, validated so it can never be the app database."""
    url = _TestSettings().TEST_DATABASE_URL.strip()
    if not url:
        pytest.exit(
            "TEST_DATABASE_URL is not set. Point it at a separate PostgreSQL database, e.g. "
            "postgresql+psycopg://<user>:<password>@localhost:5432/email_agent_test "
            "(environment variable or backend/.env).",
            returncode=2,
        )
    parsed, app_db = make_url(url), make_url(settings.DATABASE_URL)
    if not parsed.drivername.startswith("postgresql"):
        pytest.exit("TEST_DATABASE_URL must be a PostgreSQL URL.", returncode=2)
    if not (parsed.database or "").endswith("_test"):
        pytest.exit("TEST_DATABASE_URL must point to a database whose name ends with '_test'.", returncode=2)
    if (parsed.host, parsed.port, parsed.database) == (app_db.host, app_db.port, app_db.database):
        pytest.exit("TEST_DATABASE_URL must not be the application database (DATABASE_URL).", returncode=2)
    return url


test_database_url.__test__ = False  # a helper, not a test


def alembic_config(url: str) -> Config:
    """Alembic config bound explicitly to `url` (never falls back to DATABASE_URL)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.cmd_opts = type("Opts", (), {"x": [f"db_url={url}"]})()
    return config


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    for limiter in ALL_LIMITERS:
        limiter.reset()
    yield


@pytest.fixture(scope="session")
def database_url() -> str:
    return test_database_url()


@pytest.fixture(scope="session", autouse=True)
def _postgres_engine(database_url):
    # autouse: every run validates TEST_DATABASE_URL and connects to PostgreSQL up front,
    # even when the selected tests don't use the database.
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        current = connection.execute(text("SELECT current_database()")).scalar()
    assert current.endswith("_test"), f"refusing to run tests against {current!r}"

    config = alembic_config(database_url)
    command.downgrade(config, "base")  # start from an empty schema
    command.upgrade(config, "head")  # build it with the real migrations
    yield engine
    command.downgrade(config, "base")
    engine.dispose()


def _truncate_all(engine) -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def engine(_postgres_engine):
    _truncate_all(_postgres_engine)  # every test starts with empty tables
    yield _postgres_engine


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
