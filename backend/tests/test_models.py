import pytest
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.models import AccountType, Company, CompanyService, EmailAccount, EmailProvider, SecurityType, User


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
        "email_accounts",
        "email_signatures",
        "email_preferences",
        "email_history",
        "email_templates",
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


def _account(company_id, email="s@example.com", is_default=False):
    return EmailAccount(
        company_id=company_id,
        account_name="Sales",
        provider=EmailProvider.GENERIC,
        account_type=AccountType.SMTP,
        email_address=email,
        sender_name="S",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="s",
        encrypted_smtp_password="cipher",
        security_type=SecurityType.STARTTLS,
        is_default=is_default,
    )


def _company(session):
    user = _user()
    user.company = Company(name="A", description="d")
    session.add(user)
    session.commit()
    return user.company


def test_company_can_have_multiple_email_accounts(session):
    company = _company(session)
    session.add_all([_account(company.id, "a@example.com", True), _account(company.id, "b@example.com")])
    session.commit()
    assert session.query(EmailAccount).count() == 2


def test_only_one_default_email_account_per_company(session):
    company = _company(session)
    session.add_all([_account(company.id, "a@example.com", True), _account(company.id, "b@example.com", True)])
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_account_address_per_type_rejected(session):
    company = _company(session)
    session.add_all([_account(company.id, "a@example.com"), _account(company.id, "a@example.com")])
    with pytest.raises(IntegrityError):
        session.commit()


def test_account_repr_has_no_credentials(session):
    company = _company(session)
    account = _account(company.id)
    assert "cipher" not in repr(account)
