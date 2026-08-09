"""cart_items -- PLAN-02 P14

One table. The `UNIQUE (account_id, source, source_id, offer_type)` constraint is the
load-bearing part: every listing is one physical vehicle, so a cart holding two of the same
one describes something that does not exist. `Cart.with_item` already refuses it in Python;
this is the backstop, because application logic can be raced and a constraint cannot -- the
same posture `bookings.idempotency_key` takes for double-submitted checkouts.

`account_id` cascades (a deleted account's cart is meaningless), `listing_id` does not: a
withdrawn listing is soft-deleted, and a cart item whose car was pulled should surface as
unavailable at checkout rather than vanish between two page loads.

Revision ID: 0005_cart
Revises: 0004_dealers
Create Date: 2026-08-09 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_cart"
down_revision: str | None = "0004_dealers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cart_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("offer_type", sa.String(length=16), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_cart_items_account", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], name="fk_cart_items_listing"),
        sa.PrimaryKeyConstraint("id", name="pk_cart_items"),
        sa.UniqueConstraint(
            "account_id", "source", "source_id", "offer_type", name="uq_cart_items_natural"
        ),
    )
    op.create_index("ix_cart_items_account", "cart_items", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cart_items_account", table_name="cart_items")
    op.drop_table("cart_items")
