from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Company, EmailSignature
from app.schemas.signature import SignatureCreate, SignatureUpdate


class SignatureService:
    def __init__(self, db: Session):
        self.db = db

    def find(self, company: Company) -> EmailSignature | None:
        return self.db.scalar(select(EmailSignature).where(EmailSignature.company_id == company.id))

    def get(self, company: Company) -> EmailSignature:
        signature = self.find(company)
        if signature is None:
            raise NotFoundError("Email signature not found")
        return signature

    def active_signature(self, company: Company) -> EmailSignature | None:
        """The signature if it exists and is enabled, else None."""
        signature = self.find(company)
        return signature if signature is not None and signature.enabled else None

    def create(self, company: Company, data: SignatureCreate) -> EmailSignature:
        if self.find(company) is not None:
            raise ConflictError("A signature already exists. Use PUT to update it.")
        signature = EmailSignature(company_id=company.id, **data.model_dump())
        self.db.add(signature)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ConflictError("A signature already exists.")
        return signature

    def update(self, company: Company, data: SignatureUpdate) -> EmailSignature:
        signature = self.get(company)
        for field, value in data.model_dump().items():
            setattr(signature, field, value)
        self.db.commit()
        return signature

    def delete(self, company: Company) -> None:
        self.db.delete(self.get(company))
        self.db.commit()
