"""leads -- PLAN-02 P15

One table. The primary key is `lead_uuid(buyer_account_id, listing_id)` rather than a fresh
uuid, which is what makes "one lead per buyer per car" (gate 15.1) unfalsifiable: a second
insert for the same pair collides with the PK instead of quietly becoming a duplicate the
dealer has to reconcile by hand.

`dealer_id` is indexed on its own and paired with `state`, because those are the only two
shapes the console ever queries -- every read is scoped to exactly one dealer
(`src/adapters/lead_store.py`, CONSTITUTION IV.4).

`buyer_account_id` cascades (a deleted account's leads are meaningless and carry that
account's contact details). `dealer_id` and `listing_id` do not: deleting a dealer must not
silently delete the evidence of what their inventory attracted, and a withdrawn listing is
soft-deleted, so a lead about it stays readable.

Revision ID: 0006_leads
Revises: 0005_cart
Create Date: 2026-08-09 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_leads"
down_revision: str | None = "0005_cart"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("buyer_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dealer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        # The full `Lead`, score breakdown included. A "why this tier" panel that recomputed
        # from today's clock would show the dealer different reasoning than the lead was
        # scored with, which is worse than showing none.
        sa.Column("canonical", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["buyer_account_id"], ["accounts.id"], name="fk_leads_buyer", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["dealer_id"], ["dealers.id"], name="fk_leads_dealer"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], name="fk_leads_listing"),
        sa.PrimaryKeyConstraint("id", name="pk_leads"),
    )
    op.create_index("ix_leads_dealer", "leads", ["dealer_id"], unique=False)
    op.create_index("ix_leads_dealer_state", "leads", ["dealer_id", "state"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_leads_dealer_state", table_name="leads")
    op.drop_index("ix_leads_dealer", table_name="leads")
    op.drop_table("leads")
