"""`PostgresBookingStore` -- the durable path for `src/adapters/booking_store.py`'s
`BookingStore` protocol, the same split `PostgresListingStore`/`PostgresSessionStateStore`
make for their own tables.

`canonical` is the only column a `Booking` is ever rebuilt from (D-006's dual-storage shape);
`state`/`idempotency_key`/`session_id`/`listing_id` are the projected columns the idempotency
lookup and the TTL sweep filter on. The listing-hold set stays in-memory even here -- it is a
process-lifetime concurrency hint, not data anyone needs back after a restart, the same
reasoning `src/mcp/apps/audit.py`'s `AppAuditLog` already applies to its own in-memory trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.booking_store import PENDING_TTL_MINUTES, expire_stale_bookings
from src.adapters.db.models import BookingRow
from src.domain.booking import Booking, BookingState


class PostgresBookingStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        #: Not durable by design -- see this module's docstring.
        self._held_listings: set[uuid.UUID] = set()

    async def find_by_idempotency_key(
        self, session_id: uuid.UUID, idempotency_key: str
    ) -> Booking | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(BookingRow).where(
                    BookingRow.session_id == session_id,
                    BookingRow.idempotency_key == idempotency_key,
                )
            )
        return _to_booking(row) if row is not None else None

    async def insert(self, booking: Booking) -> Booking:
        async with self._sessions() as session:
            session.add(_to_row(booking))
            try:
                await session.commit()
            except IntegrityError:
                # The UNIQUE(session_id, idempotency_key) constraint is the backstop
                # (PHASE-8 §6) -- a race that slipped past the in-process check lands here
                # instead of becoming a second booking.
                await session.rollback()
                existing = await self.find_by_idempotency_key(
                    booking.session_id, booking.idempotency_key
                )
                if existing is not None:
                    return existing
                raise
        if booking.state is BookingState.PENDING:
            self._held_listings.add(booking.listing_id)
        return booking

    async def update(self, booking: Booking) -> None:
        async with self._sessions() as session:
            row = await session.get(BookingRow, booking.id)
            if row is None:
                session.add(_to_row(booking))
            else:
                row.state = booking.state.value
                row.canonical = booking.model_dump(mode="json")
                row.updated_at = booking.updated_at
            await session.commit()
        if booking.state is BookingState.PENDING:
            self._held_listings.add(booking.listing_id)
        else:
            self._held_listings.discard(booking.listing_id)

    async def get(self, booking_id: uuid.UUID) -> Booking | None:
        async with self._sessions() as session:
            row = await session.get(BookingRow, booking_id)
        return _to_booking(row) if row is not None else None

    async def pending_since(self) -> tuple[tuple[uuid.UUID, datetime], ...]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(BookingRow).where(BookingRow.state == BookingState.PENDING.value)
            )
            return tuple((row.id, row.created_at) for row in rows)

    def is_held(self, listing_id: uuid.UUID) -> bool:
        return listing_id in self._held_listings

    async def expire_stale(
        self, *, ttl_minutes: int = PENDING_TTL_MINUTES, now: datetime | None = None
    ) -> tuple[Booking, ...]:
        return await expire_stale_bookings(self, ttl_minutes=ttl_minutes, now=now)


def _to_row(booking: Booking) -> BookingRow:
    return BookingRow(
        id=booking.id,
        session_id=booking.session_id,
        listing_id=booking.listing_id,
        state=booking.state.value,
        idempotency_key=booking.idempotency_key,
        canonical=booking.model_dump(mode="json"),
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )


def _to_booking(row: BookingRow) -> Booking:
    return Booking.model_validate(row.canonical)
