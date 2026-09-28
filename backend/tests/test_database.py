from sqlalchemy import create_engine, text

from app.db.database import engine


def test_engine_hides_bound_parameters():
    assert engine.hide_parameters is True


def test_sqlalchemy_session_roundtrip():
    test_engine = create_engine("sqlite://")
    with test_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1
