"""The Postgres schema (PHASE-1 §6).

P1 owns the schema for the whole application, not just for listings -- P0 deliberately
owned the *models* and left migrations here so there is exactly one place the tables are
declared. `sessions`, `decisions`, `memories` and `bookings` are created now and filled in
by P3, P5, P4 and P8 respectively; creating them up front costs one migration and saves
four.

The `listings` table carries both projected columns and a `canonical` JSONB document. That
looks like duplication and is deliberate: the columns are what structured search filters
and sorts on (indexed, straight SQL), while `canonical` is what a `Listing` is rebuilt
from. Reconstructing a 30-field Pydantic model column by column is where mapping bugs live,
and gate 1.7 asserts every row validates.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ListingRow(Base):
    __tablename__ = "listings"
    __table_args__ = (
        # The deduplication primitive: when two marketplaces list the same vehicle, this is
        # what makes "same listing" a decidable question (PHASE-1 §6).
        UniqueConstraint("source", "source_id", name="uq_listings_source_source_id"),
        Index("ix_listings_category_offer", "category", "offer_type"),
        Index("ix_listings_brand", "brand"),
        Index("ix_listings_market_value", "market_value_amount"),
        Index("ix_listings_year", "year"),
        Index("ix_listings_mileage", "mileage_km"),
        Index("ix_listings_available_from", "available_from"),
        # Partial index: almost every query excludes withdrawn rows, and they are a small
        # minority, so the live set is what deserves the index.
        Index(
            "ix_listings_live",
            "source",
            postgresql_where=text("withdrawn_at IS NULL"),
        ),
        CheckConstraint("mileage_km >= 0", name="ck_listings_mileage_non_negative"),
        CheckConstraint("insurance_band BETWEEN 1 AND 20", name="ck_listings_insurance_band"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Soft delete, so a booking that references a pulled listing still resolves.
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: PLAN-02 P13. Nullable at the column level so the migration lands on an already-seeded
    #: database without a destructive rewrite; the re-seed fills it, and gate 13.1 asserts
    #: zero orphans in a freshly generated catalogue rather than trusting the constraint.
    dealer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dealers.id"), index=True
    )

    brand: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    variant: Mapped[str] = mapped_column(String(64), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    #: PLAN-02 P13 / proposal doc #2. Server default `used`, matching `Listing.condition`'s
    #: own default -- the safe direction for rows that predate this column.
    condition: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="used", index=True
    )
    offer_type: Mapped[str] = mapped_column(String(16), nullable=False)

    market_value_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    market_value_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_buy_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rental_daily_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    mileage_km: Mapped[int] = mapped_column(Integer, nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(16), nullable=False)
    transmission: Mapped[str] = mapped_column(String(16), nullable=False)
    seats: Mapped[int] = mapped_column(Integer, nullable=False)
    doors: Mapped[int] = mapped_column(Integer, nullable=False)

    insurance_band: Mapped[int] = mapped_column(Integer, nullable=False)
    service_interval_km: Mapped[int | None] = mapped_column(Integer)
    timing_mechanism: Mapped[str] = mapped_column(String(8), nullable=False)
    powertrain_archetype: Mapped[str] = mapped_column(String(24), nullable=False)

    city: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    available_from: Mapped[date] = mapped_column(Date, nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False)

    #: The untouched upstream payload (CONSTITUTION II.6 / PHASE-0 §4).
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: The full normalised `Listing`, and the only thing `to_listing` reads.
    canonical: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class DealerRow(Base):
    """PLAN-02 P13. The business behind a listing.

    `canonical` carries the whole `Dealer` (D-006's dual-storage shape, same as `listings`);
    the projected columns are the ones a query filters on -- `source`/`city` for the
    directory view, `verification_status` because P14's checkout has to be able to find
    unverified payees without deserialising every row.
    """

    __tablename__ = "dealers"
    __table_args__ = (
        UniqueConstraint("source", "dealer_ref", name="uq_dealers_source_ref"),
        Index("ix_dealers_source_city", "source", "city"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    dealer_ref: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class ListingVectorRow(Base):
    """[SCALE] pgvector over the composed description. Table created now, filled by P1's
    semantic-search work if P5 lands early -- the structured path alone is enough for the
    hackathon (PHASE-1 §8).
    """

    __tablename__ = "listing_vectors"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    #: Declared in the migration as `vector(768)`; typed loosely here so importing this
    #: module never requires the pgvector Python package to be installed.
    embedding: Mapped[Any] = mapped_column(JSONB, nullable=False)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionRow(Base):
    """Append-only. Never updated in place -- see `DecisionEntry`."""

    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_session_turn", "session_id", "turn"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryRow(Base):
    __tablename__ = "memories"
    __table_args__ = (Index("ix_memories_user_kind", "user_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Supersede rather than update, so "why did it think that?" stays answerable.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))


class AccountRow(Base):
    """PLAN-02 P12. Identity is `(email, role)`, not `email` -- one person may hold a buyer
    account and a seller account on one address, and the constraint below is what makes that
    a supported case rather than a collision (`src/adapters/identity_store.py`'s docstring).
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("email", "role", name="uq_accounts_email_role"),
        Index("ix_accounts_role", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountProfileRow(Base):
    """The role-specific half, stored as one `canonical` document -- the same dual-storage
    shape D-006 gave `listings` and D-014 gave `sessions.profile`.

    Whole-document rather than projected columns because nothing queries *into* a profile:
    the API reads it by `account_id` and hands it back. `annual_income` living inside JSONB
    also means it has exactly one home to redact from, rather than a column that a future
    `SELECT *` in a log line could surface (PLAN-02 §0.3).
    """

    __tablename__ = "account_profiles"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class AuthTokenRow(Base):
    """An opaque bearer token. No JWT, no signature, no secret (PLAN-02 §0.2) -- the token
    *is* the lookup key, so there is nothing to forge offline and nothing to leak from the
    repository.
    """

    __tablename__ = "auth_tokens"
    __table_args__ = (Index("ix_auth_tokens_account", "account_id"),)

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CartItemRow(Base):
    """PLAN-02 P14. One row per car in one account's shortlist.

    `UNIQUE (account_id, source, source_id, offer_type)` is the database-level half of
    `Cart.with_item`'s idempotency: every listing is one physical vehicle, so a cart holding
    two of the same one is describing something that does not exist. Application logic can be
    raced; this constraint cannot -- the same backstop posture `bookings.idempotency_key`
    takes for double-submitted checkouts.
    """

    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "source", "source_id", "offer_type", name="uq_cart_items_natural"
        ),
        Index("ix_cart_items_account", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    #: No ON DELETE CASCADE: a withdrawn listing is soft-deleted, so this always resolves --
    #: and a cart item whose car was pulled should show as unavailable at checkout (gate
    #: 14.10), not vanish silently between one page load and the next.
    listing_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("listings.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    offer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OtpChallengeRow(Base):
    """A started login. Persisted rather than held in-process so `request-otp` and
    `verify-otp` landing on two different workers still describe one flow -- the failure
    mode an in-memory challenge store hides on a single-worker dev machine and exposes the
    moment the API scales past one.
    """

    __tablename__ = "otp_challenges"

    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BookingRow(Base):
    """PHASE-8 §3/§6. `state`/`idempotency_key`/`listing_id`/`session_id` are projected
    columns -- what the idempotency lookup and the TTL sweep query filter on -- and
    `canonical` is the full `Booking` a row is rebuilt from, the same dual-storage shape
    D-006 established for `listings` and D-014 reused for `sessions.profile`.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        # Idempotency is per session, and it is what stops a double-submitted checkout
        # becoming two bookings (P8, gate 8.5). The database is the backstop; application
        # logic can race, this constraint cannot.
        UniqueConstraint("session_id", "idempotency_key", name="uq_bookings_idempotency"),
        Index("ix_bookings_state", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    #: No ON DELETE CASCADE: a withdrawn listing is soft-deleted, so this always resolves.
    listing_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("listings.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The full `Booking.model_dump(mode="json")`, audit trail included -- `canonical` is the
    #: only thing a `Booking` is ever rebuilt from (mirrors `ListingRow.canonical`).
    canonical: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LeadRow(Base):
    """PLAN-02 P15. One row per (buyer, car) engagement, routed to the dealer who owns it.

    `id` is `lead_uuid(buyer_account_id, listing_id)` -- deterministic, so "one lead per buyer
    per car" (gate 15.1) is a property of the primary key rather than of an upsert somebody
    has to keep correct. A `UNIQUE` on the pair would say the same thing twice.

    `dealer_id` is indexed because it is the *only* way leads are ever read: every query is
    scoped to one dealer (`LeadStore`'s own note, CONSTITUTION IV.4), so an unindexed scan
    here would be a table scan on the hottest seller-facing path.

    `tier`/`score`/`state` are projected columns -- what the console sorts and filters on --
    and `canonical` is the full `Lead`, score breakdown included, the same dual-storage shape
    D-006 established for `listings`. The breakdown has to survive a restart intact: a "why
    this tier" panel that recomputed from today's clock would show a dealer different
    reasoning than the lead was actually scored with.
    """

    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_dealer", "dealer_id"),
        Index("ix_leads_dealer_state", "dealer_id", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    buyer_account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    #: RESTRICT, not CASCADE: deleting a dealer must not silently delete the leads that prove
    #: what their inventory attracted (the same posture `listings.dealer_id` takes, D-075).
    dealer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dealers.id"), nullable=False
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("listings.id"), nullable=False
    )
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
