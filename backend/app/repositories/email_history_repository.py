import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EmailHistory, EmailStatus


class EmailHistoryRepository:
    """Every query is filtered by company_id."""

    def __init__(self, db: Session):
        self.db = db

    def list_for_company(
        self, company_id: uuid.UUID, *, offset: int, limit: int, status: EmailStatus | None = None
    ) -> tuple[list[EmailHistory], int]:
        filters = [EmailHistory.company_id == company_id]
        if status is not None:
            filters.append(EmailHistory.status == status)
        total = self.db.scalar(select(func.count(EmailHistory.id)).where(*filters)) or 0
        items = self.db.scalars(
            select(EmailHistory)
            .where(*filters)
            .order_by(EmailHistory.created_at.desc(), EmailHistory.id)
            .offset(offset)
            .limit(limit)
        ).all()
        return list(items), total

    def get_for_company(self, company_id: uuid.UUID, history_id: uuid.UUID) -> EmailHistory | None:
        return self.db.scalar(
            select(EmailHistory).where(EmailHistory.id == history_id, EmailHistory.company_id == company_id)
        )
