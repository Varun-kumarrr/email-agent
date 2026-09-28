"""oauth states for CSRF-safe OAuth connections

Revision ID: 0005_oauth_states
Revises: 0004_email_delivery_status
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_oauth_states"
down_revision: Union[str, Sequence[str], None] = "0004_email_delivery_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_states",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "provider", sa.Enum("GMAIL", "OUTLOOK", "GENERIC", name="emailprovider", native_enum=False, length=20), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_oauth_states_company_id_companies"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_oauth_states_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_states")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_oauth_states_state_hash")),
    )
    op.create_index(op.f("ix_oauth_states_company_id"), "oauth_states", ["company_id"], unique=False)
    op.create_index(op.f("ix_oauth_states_expires_at"), "oauth_states", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_oauth_states_expires_at"), table_name="oauth_states")
    op.drop_index(op.f("ix_oauth_states_company_id"), table_name="oauth_states")
    op.drop_table("oauth_states")
