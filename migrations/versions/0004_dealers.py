"""dealers directory + listing dealer_id/condition -- PLAN-02 P13

Creates `dealers` and adds two columns to `listings`. Both new listing columns land in a
shape that is safe on an already-seeded database:

- `dealer_id` is **nullable**. The dealer a listing belongs to is decided by the deterministic
  generator (`src/adapters/catalogue/generator.py`), not by anything SQL can recompute from
  the existing row, so there is no honest in-migration backfill to write. Re-running
  `python -m scripts.seed_marketplace` (which upserts on `(source, source_id)`) fills it, and
  the compose `command` already runs a seed on every start. Gate 13.1 asserts zero orphans in
  a freshly generated catalogue, which is the property that actually matters.
- `condition` is **NOT NULL with a `used` server default**, matching `Listing.condition`'s own
  default. Rows that predate this column are genuinely of unknown condition, and `used` is
  the value that over-promises least (an unlabelled second-hand car described as new is a
  claim nobody made).

The `dealer_id` foreign key deliberately has no `ON DELETE CASCADE`: deleting a dealer must
not silently delete their inventory. It is `RESTRICT` by omission, which turns that into a
loud error instead of lost rows.

Revision ID: 0004_dealers
Revises: 0003_identity
Create Date: 2026-08-09 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_dealers"
down_revision: str | None = "0003_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dealers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("dealer_ref", sa.String(length=32), nullable=False),
        sa.Column("legal_name", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("canonical", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dealers"),
        sa.UniqueConstraint("source", "dealer_ref", name="uq_dealers_source_ref"),
    )
    op.create_index("ix_dealers_source_city", "dealers", ["source", "city"], unique=False)

    op.add_column(
        "listings", sa.Column("dealer_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_listings_dealer", "listings", "dealers", ["dealer_id"], ["id"]
    )
    op.create_index("ix_listings_dealer", "listings", ["dealer_id"], unique=False)

    op.add_column(
        "listings",
        sa.Column("condition", sa.String(length=24), nullable=False, server_default="used"),
    )
    op.create_index("ix_listings_condition", "listings", ["condition"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_listings_condition", table_name="listings")
    op.drop_column("listings", "condition")
    op.drop_index("ix_listings_dealer", table_name="listings")
    op.drop_constraint("fk_listings_dealer", "listings", type_="foreignkey")
    op.drop_column("listings", "dealer_id")
    op.drop_index("ix_dealers_source_city", table_name="dealers")
    op.drop_table("dealers")
