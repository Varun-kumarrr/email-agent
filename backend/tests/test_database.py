from sqlalchemy import make_url, text

from app.core.config import settings
from app.db.database import engine as app_engine


def test_engine_hides_bound_parameters():
    assert app_engine.hide_parameters is True


def test_application_database_is_postgresql():
    assert make_url(settings.DATABASE_URL).get_backend_name() == "postgresql"


def test_suite_is_connected_to_the_postgresql_test_database(engine):
    """Proves the tests really run on PostgreSQL, in the *_test database, not the app database."""
    assert engine.dialect.name == "postgresql"
    with engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar()
        version = connection.execute(text("SHOW server_version")).scalar()
    assert database.endswith("_test")
    assert database != make_url(settings.DATABASE_URL).database
    assert version  # a real PostgreSQL server answered
