"""mark account test emails in email history

Revision ID: 0006_history_is_test
Revises: 0005_oauth_states
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_history_is_test"
down_revision: Union[str, Sequence[str], None] = "0005_oauth_states"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows are real emails, so the default is false.
    op.add_column("email_history", sa.Column("is_test", sa.Boolean(), server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    op.drop_column("email_history", "is_test")
