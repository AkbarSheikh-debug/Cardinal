"""bookings commerce columns -- PHASE-8 section 6

P0/P1 pre-created `bookings` with the columns P3's session/listing FKs and P8's own idempotency
constraint needed up front (`state`, `idempotency_key`, `audit`, `ts`). P8 is the first phase to
actually write rows, and gate 8.1's exhaustive state machine plus gate 8.5's idempotency replay
need the *whole* `Booking` back, not just its projected columns -- the same dual-storage shape
D-006 gave `listings` and D-014 gave `sessions.profile`. `ts` (a single "last touched" timestamp)
and the bare `audit` array are both superseded by `created_at`/`updated_at` and `canonical`
(which already carries the full audit trail as part of the whole `Booking`); nothing in the
codebase read either column before this migration, so there is no mapping to preserve.

Revision ID: 0002_bookings_commerce
Revises: 0001_initial
Create Date: 2026-08-08 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_bookings_commerce"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("canonical", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "bookings", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    # `bookings` has no rows before P8 (nothing wrote to it), so a straight backfill from
    # `ts` is enough to let the three new columns go NOT NULL in the same migration rather
    # than a slower two-step "add nullable, backfill, tighten" across two releases.
    op.execute(
        "UPDATE bookings SET canonical = '{}'::jsonb, created_at = ts, updated_at = ts "
        "WHERE canonical IS NULL"
    )
    op.alter_column("bookings", "canonical", nullable=False)
    op.alter_column("bookings", "created_at", nullable=False)
    op.alter_column("bookings", "updated_at", nullable=False)
    op.drop_column("bookings", "ts")
    op.drop_column("bookings", "audit")
    op.create_index("ix_bookings_state", "bookings", ["state"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bookings_state", table_name="bookings")
    op.add_column(
        "bookings",
        sa.Column(
            "audit", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
    )
    op.alter_column("bookings", "audit", server_default=None)
    op.add_column("bookings", sa.Column("ts", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE bookings SET ts = updated_at WHERE ts IS NULL")
    op.alter_column("bookings", "ts", nullable=False)
    op.drop_column("bookings", "updated_at")
    op.drop_column("bookings", "created_at")
    op.drop_column("bookings", "canonical")
