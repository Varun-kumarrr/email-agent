import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Company


class CompanyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: uuid.UUID) -> Company | None:
        """The only way companies are looked up: by the authenticated owner."""
        return self.db.scalar(
            select(Company)
            .where(Company.user_id == user_id)
            .options(
                selectinload(Company.services),
                selectinload(Company.target_customers),
                selectinload(Company.value_propositions),
                selectinload(Company.social_links),
            )
        )

    def add(self, company: Company) -> Company:
        self.db.add(company)
        self.db.flush()
        return company
