import pytest
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.models import Company, CompanyService, EmailConfiguration, SecurityType, User


@pytest.fixture()
def session(db_session):
    # The shared PostgreSQL test session (tables emptied before each test).
    yield db_session
    db_session.rollback()


def _user(email="a@example.com"):
    return User(email=email, name="A", hashed_password="x")


def test_expected_tables_exist():
    assert set(Base.metadata.tables) == {
        "users",
        "companies",
        "company_services",
        "target_customers",
        "value_propositions",
        "social_links",
        "email_configurations",
        "email_signatures",
        "email_preferences",
        "email_history",
    }


def test_company_with_children_and_cascade_delete(session):
    user = _user()
    user.company = Company(
        name="ABC", description="CRM", services=[CompanyService(name="CRM")]
    )
    session.add(user)
    session.commit()
    assert session.query(CompanyService).count() == 1

    session.delete(user)
    session.commit()
    assert session.query(Company).count() == 0
    assert session.query(CompanyService).count() == 0


def test_user_can_only_own_one_company(session):
    user = _user()
    session.add(user)
    session.commit()
    session.add_all(
        [Company(user_id=user.id, name="A", description="d"), Company(user_id=user.id, name="B", description="d")]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_user_email_rejected(session):
    session.add_all([_user(), _user()])
    with pytest.raises(IntegrityError):
        session.commit()


def test_one_email_configuration_per_company(session):
    user = _user()
    user.company = Company(name="A", description="d")
    session.add(user)
    session.commit()
    for _ in range(2):
        session.add(
            EmailConfiguration(
                company_id=user.company.id,
                email="s@example.com",
                smtp_host="smtp.example.com",
                smtp_port=587,
                username="s",
                encrypted_password="cipher",
                security_type=SecurityType.STARTTLS,
                sender_name="S",
            )
        )
    with pytest.raises(IntegrityError):
        session.commit()
