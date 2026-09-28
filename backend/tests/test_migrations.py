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
