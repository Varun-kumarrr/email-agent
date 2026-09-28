"""Verify the Alembic migrations build exactly the schema described by the ORM models."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db.base import Base
import app.models  # noqa: F401

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"db_url={db_url}"]})()
    return cfg


def test_upgrade_matches_models_and_downgrade_removes_tables(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
    cfg = _config(db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], f"Models and migrations are out of sync: {diff}"

    command.downgrade(cfg, "base")
    remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert remaining == set()
    engine.dispose()
