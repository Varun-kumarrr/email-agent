"""multiple email accounts per company

Replaces the single per-company `email_configurations` row with `email_accounts`
(many per company, at most one default, SMTP or OAuth), copies existing
configurations across (keeping their IDs), and links email history to the
account that sent each email.

Revision ID: 0002_email_accounts
Revises: 0001_initial_schema
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_email_accounts"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(*values, name):
    return sa.Enum(*values, name=name, native_enum=False, length=20)


def upgrade() -> None:
    op.create_table(
        "email_accounts",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("account_name", sa.String(length=120), nullable=False),
        sa.Column("provider", _enum("GMAIL", "OUTLOOK", "GENERIC", name="emailprovider"), nullable=False),
        sa.Column("account_type", _enum("SMTP", "OAUTH", name="accounttype"), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=False),
        sa.Column("sender_name", sa.String(length=120), nullable=False),
        sa.Column("reply_to", sa.String(length=255), nullable=True),
        sa.Column("smtp_host", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_username", sa.String(length=255), nullable=True),
        sa.Column("encrypted_smtp_password", sa.Text(), nullable=True),
        sa.Column("security_type", _enum("NONE", "STARTTLS", "SSL_TLS", name="securitytype"), nullable=True),
        sa.Column("encrypted_oauth_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_oauth_refresh_token", sa.Text(), nullable=True),
        sa.Column("oauth_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oauth_scopes", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_success", sa.Boolean(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_email_accounts_company_id_companies"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_accounts")),
        sa.UniqueConstraint(
            "company_id", "account_type", "email_address", name="uq_email_accounts_company_type_email"
        ),
    )
    op.create_index(op.f("ix_email_accounts_company_id"), "email_accounts", ["company_id"], unique=False)
    op.create_index(
        "uq_email_accounts_one_default_per_company",
        "email_accounts",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    # Carry existing single configurations over as each company's default SMTP account.
    op.execute(
        """
        INSERT INTO email_accounts (
            id, company_id, account_name, provider, account_type, email_address, sender_name, reply_to,
            smtp_host, smtp_port, smtp_username, encrypted_smtp_password, security_type,
            is_active, is_default, last_tested_at, last_test_success, created_at, updated_at
        )
        SELECT
            id, company_id, 'Primary SMTP',
            CASE
                WHEN lower(smtp_host) LIKE '%gmail.com' OR lower(smtp_host) LIKE '%googlemail.com' THEN 'GMAIL'
                WHEN lower(smtp_host) LIKE '%office365.com' OR lower(smtp_host) LIKE '%outlook.com' THEN 'OUTLOOK'
                ELSE 'GENERIC'
            END,
            'SMTP', lower(email), sender_name, reply_to,
            smtp_host, smtp_port, username, encrypted_password, security_type,
            true, true, last_tested_at, last_test_success, created_at, updated_at
        FROM email_configurations
        """
    )

    op.add_column("email_history", sa.Column("email_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_email_history_email_account_id_email_accounts"),
        "email_history",
        "email_accounts",
        ["email_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_email_history_email_account_id"), "email_history", ["email_account_id"], unique=False)
    # Before this migration each company had exactly one account, so it sent every past email.
    op.execute(
        """
        UPDATE email_history h SET email_account_id = a.id
        FROM email_accounts a
        WHERE a.company_id = h.company_id AND a.is_default
        """
    )

    op.drop_table("email_configurations")


def downgrade() -> None:
    op.create_table(
        "email_configurations",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("smtp_host", sa.String(length=255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("security_type", _enum("NONE", "STARTTLS", "SSL_TLS", name="securitytype"), nullable=False),
        sa.Column("sender_name", sa.String(length=120), nullable=False),
        sa.Column("reply_to", sa.String(length=255), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_success", sa.Boolean(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_email_configurations_company_id_companies"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_configurations")),
        sa.UniqueConstraint("company_id", name=op.f("uq_email_configurations_company_id")),
    )
    # Keep one SMTP account per company (the default if it is SMTP, else the oldest SMTP account).
    op.execute(
        """
        INSERT INTO email_configurations (
            id, company_id, email, smtp_host, smtp_port, username, encrypted_password, security_type,
            sender_name, reply_to, last_tested_at, last_test_success, created_at, updated_at
        )
        SELECT DISTINCT ON (company_id)
            id, company_id, email_address, smtp_host, smtp_port, smtp_username, encrypted_smtp_password,
            security_type, sender_name, reply_to, last_tested_at, last_test_success, created_at, updated_at
        FROM email_accounts
        WHERE account_type = 'SMTP'
        ORDER BY company_id, is_default DESC, created_at
        """
    )
    op.drop_index(op.f("ix_email_history_email_account_id"), table_name="email_history")
    op.drop_constraint(op.f("fk_email_history_email_account_id_email_accounts"), "email_history", type_="foreignkey")
    op.drop_column("email_history", "email_account_id")
    op.drop_index("uq_email_accounts_one_default_per_company", table_name="email_accounts")
    op.drop_index(op.f("ix_email_accounts_company_id"), table_name="email_accounts")
    op.drop_table("email_accounts")
