"""identity: accounts, profiles, tokens, otp challenges -- PLAN-02 P12

Four tables, no changes to anything P0-P11 created. `accounts` is the first table in this
schema that holds personal data about a *person* rather than a vehicle or a session, which
is why `account_profiles.canonical` is one JSONB document instead of projected columns:
`annual_income` then has exactly one home to redact from (PLAN-02 §0.3), rather than a
column a future `SELECT *` could surface into a log line.

`UNIQUE (email, role)` rather than `UNIQUE (email)` is deliberate -- a dealer who also buys
a car holds two accounts on one address, and that is a supported case, not a collision.

Revision ID: 0003_identity
Revises: 0002_bookings_commerce
Create Date: 2026-08-09 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_identity"
down_revision: str | None = "0002_bookings_commerce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.UniqueConstraint("email", "role", name="uq_accounts_email_role"),
    )
    op.create_index("ix_accounts_role", "accounts", ["role"], unique=False)

    op.create_table(
        "account_profiles",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("canonical", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_account_profiles_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name="pk_account_profiles"),
    )

    op.create_table(
        "auth_tokens",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_auth_tokens_account", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("token", name="pk_auth_tokens"),
    )
    op.create_index("ix_auth_tokens_account", "auth_tokens", ["account_id"], unique=False)

    op.create_table(
        "otp_challenges",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("email", "role", name="pk_otp_challenges"),
    )


def downgrade() -> None:
    op.drop_table("otp_challenges")
    op.drop_index("ix_auth_tokens_account", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_table("account_profiles")
    op.drop_index("ix_accounts_role", table_name="accounts")
    op.drop_table("accounts")
