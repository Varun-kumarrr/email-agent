"""reusable email templates

Revision ID: 0003_email_templates
Revises: 0002_email_accounts
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_email_templates"
down_revision: Union[str, Sequence[str], None] = "0002_email_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_templates",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=True),
        sa.Column("subject_template", sa.String(length=300), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column(
            "content_type", sa.Enum("HTML", "PLAIN_TEXT", name="emailformat", native_enum=False, length=20), nullable=False
        ),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_email_templates_company_id_companies"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_templates")),
        sa.UniqueConstraint("company_id", "name", name="uq_email_templates_company_name"),
    )
    op.create_index(op.f("ix_email_templates_company_id"), "email_templates", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_templates_company_id"), table_name="email_templates")
    op.drop_table("email_templates")
