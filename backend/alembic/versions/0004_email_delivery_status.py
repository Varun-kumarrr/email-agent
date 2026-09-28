"""background delivery: history delivery columns

Adds reply_to, error_code, task_id and last_attempt_at to email_history so a
background worker can deliver a stored email and record its progress. The status
column gains QUEUED/SENDING/RETRYING values (VARCHAR, no schema change needed),
and the default for attempts becomes 0 (attempts are counted as they happen).

Revision ID: 0004_email_delivery_status
Revises: 0003_email_templates
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_email_delivery_status"
down_revision: Union[str, Sequence[str], None] = "0003_email_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("email_history", sa.Column("reply_to", sa.String(length=255), nullable=True))
    op.add_column("email_history", sa.Column("error_code", sa.String(length=60), nullable=True))
    op.add_column("email_history", sa.Column("task_id", sa.String(length=64), nullable=True))
    op.add_column("email_history", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Emails still in flight cannot be represented by the old SENT/FAILED model.
    op.execute(
        "UPDATE email_history SET status = 'FAILED', error_message = 'Delivery interrupted by a schema downgrade' "
        "WHERE status IN ('QUEUED', 'SENDING', 'RETRYING')"
    )
    op.drop_column("email_history", "last_attempt_at")
    op.drop_column("email_history", "task_id")
    op.drop_column("email_history", "error_code")
    op.drop_column("email_history", "reply_to")
