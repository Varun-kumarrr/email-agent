from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Company, CompanyService, SocialLink, TargetCustomer, User, ValueProposition
from app.repositories.company_repository import CompanyRepository
from app.schemas.company import CompanyCreate, CompanyUpdate

_SCALAR_FIELDS = (
    "name",
    "description",
    "website",
    "industry",
    "location",
    "contact_person",
    "contact_email",
    "contact_phone",
    "address",
)


def _apply(company: Company, data: CompanyCreate | CompanyUpdate) -> None:
    for field in _SCALAR_FIELDS:
        setattr(company, field, getattr(data, field))

    # Lists are replaced wholesale; delete-orphan cascade removes old rows.
    company.services = [
        CompanyService(name=s.name, description=s.description, position=i)
        for i, s in enumerate(data.services)
    ]
    company.target_customers = [
        TargetCustomer(segment=t.segment, description=t.description, position=i)
        for i, t in enumerate(data.target_customers)
    ]
    company.value_propositions = [
        ValueProposition(statement=v.statement, position=i)
        for i, v in enumerate(data.value_propositions)
    ]
    seen_urls: set[str] = set()
    links = []
    for i, link in enumerate(data.social_links):
        if link.url in seen_urls:
            continue
        seen_urls.add(link.url)
        links.append(SocialLink(platform=link.platform, url=link.url, position=i))
    company.social_links = links


class CompanyProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.companies = CompanyRepository(db)

    def get_for_user(self, user: User) -> Company:
        company = self.companies.get_by_user_id(user.id)
        if company is None:
            raise NotFoundError("Company profile not found. Create your company profile first.")
        return company

    def create(self, user: User, data: CompanyCreate) -> Company:
        if self.companies.get_by_user_id(user.id) is not None:
            raise ConflictError("A company profile already exists for this account. Use PUT to update it.")
        company = Company(user_id=user.id)
        _apply(company, data)
        try:
            self.companies.add(company)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ConflictError("A company profile already exists for this account.")
        return self.get_for_user(user)

    def update(self, user: User, data: CompanyUpdate) -> Company:
        company = self.get_for_user(user)
        # Remove old child rows first so re-adding an identical social link URL
        # does not collide with the (company_id, url) unique constraint.
        company.services.clear()
        company.target_customers.clear()
        company.value_propositions.clear()
        company.social_links.clear()
        self.db.flush()
        _apply(company, data)
        self.db.commit()
        self.db.expire(company)
        return self.get_for_user(user)
