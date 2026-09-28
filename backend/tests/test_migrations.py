"""Verify the Alembic migrations build exactly the schema described by the ORM models (PostgreSQL)."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

import app.models  # noqa: F401
from app.db.base import Base
from tests.conftest import alembic_config


def test_downgrade_then_upgrade_matches_models(engine, database_url):
    config = alembic_config(database_url)
    try:
        command.downgrade(config, "base")
        remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
        assert remaining == set()

        command.upgrade(config, "head")
        with engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert diff == [], f"Models and migrations are out of sync: {diff}"
        assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
    finally:
        command.upgrade(config, "head")  # leave the schema in place for the other tests


def test_0002_copies_single_configuration_into_default_account(engine, database_url):
    """Data migration: an existing email_configurations row becomes the default SMTP account."""
    import uuid

    from sqlalchemy import text

    config = alembic_config(database_url)
    user_id, company_id, config_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        command.downgrade(config, "0001_initial_schema")
        with engine.begin() as c:
            c.execute(text("INSERT INTO users (id, email, name, hashed_password, is_active, created_at, updated_at) "
                           "VALUES (:id, 'm@example.com', 'M', 'x', true, now(), now())"), {"id": user_id})
            c.execute(text("INSERT INTO companies (id, user_id, name, description, created_at, updated_at) "
                           "VALUES (:id, :u, 'C', 'd', now(), now())"), {"id": company_id, "u": user_id})
            c.execute(text(
                "INSERT INTO email_configurations (id, company_id, email, smtp_host, smtp_port, username, "
                "encrypted_password, security_type, sender_name, created_at, updated_at) VALUES "
                "(:id, :c, 'Me@Example.com', 'smtp.gmail.com', 587, 'me', 'ciphertext', 'STARTTLS', 'Me', now(), now())"
            ), {"id": config_id, "c": company_id})
            c.execute(text(
                "INSERT INTO email_history (id, company_id, sender_email, recipient, cc, bcc, subject, body, "
                "email_format, status, attempts, created_at, updated_at) VALUES (:id, :c, 'me@example.com', "
                "'r@example.com', '[]', '[]', 's', 'b', 'PLAIN_TEXT', 'SENT', 1, now(), now())"
            ), {"id": uuid.uuid4(), "c": company_id})

        command.upgrade(config, "head")
        with engine.connect() as c:
            row = c.execute(text(
                "SELECT id, provider, account_type, email_address, encrypted_smtp_password, is_default, is_active "
                "FROM email_accounts WHERE company_id = :c"
            ), {"c": company_id}).one()
            linked = c.execute(text("SELECT email_account_id FROM email_history WHERE company_id = :c"), {"c": company_id}).scalar()
        assert row.id == config_id
        assert (row.provider, row.account_type, row.email_address) == ("GMAIL", "SMTP", "me@example.com")
        assert row.encrypted_smtp_password == "ciphertext" and row.is_default and row.is_active
        assert linked == config_id
    finally:
        command.upgrade(config, "head")
        with engine.begin() as c:
            c.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
