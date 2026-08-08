"""Where bookings live, behind an interface -- the same split `src/adapters/store.py` makes
for listings: one `BookingStore` protocol, an in-memory implementation for tests/`DEMO_MODE`,
and a Postgres implementation (`src/adapters/db/booking_store.py`) behind the identical shape.

Two responsibilities live here beyond plain persistence, both PHASE-8 `[MVP]` requirements
that have nowhere else to go:

- **Idempotency** (PHASE-8 §6): `find_by_idempotency_key` is what lets `confirm_booking`
  answer "have I already done this?" *before* touching the payment gateway a second time.
- **The inventory hold** (PHASE-8 §3: "an abandoned checkout must not hold inventory
  forever... then EXPIRED, then the listing is released"). A hold is purely a booking-lifecycle
  concept -- nothing about *which* listings are bookable belongs on `Listing` itself
  (D-005 already made this call for rental blackout windows) -- so it lives here as a small
  in-memory set, `[MVP]`-scoped like P4's and P7's own first working stores.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from src.domain.booking import Booking, BookingEvent, BookingState, new_audit_entry, stale_pending

#: PHASE-8 §3: "15 minutes, then EXPIRED, then the listing is released."
PENDING_TTL_MINUTES = 15


def session_ref_to_uuid(session_id: str) -> uuid.UUID:
    """`booking-mcp`'s own `session_id` is a plain string (same as `SessionState.session_id`,
    PHASE-3 §3) -- not guaranteed parseable as a UUID, since gate/test session ids like
    `"t1"` or `f"gate75"` aren't. `Booking.session_id` is a real `uuid.UUID` field, so a
    non-UUID id is deterministically derived into one rather than raising, the identical
    `uuid5` coercion D-019 already established for `src/agent/journal.py`'s `session_uuid` --
    duplicated rather than imported, since `src/adapters` sits beneath `src/agent` and
    importing upward would invert the layering for a five-line function.
    """
    try:
        return uuid.UUID(session_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, session_id)


class BookingStore(Protocol):
    async def find_by_idempotency_key(
        self, session_id: uuid.UUID, idempotency_key: str
    ) -> Booking | None: ...

    async def insert(self, booking: Booking) -> Booking:
        """Inserts a brand-new booking (already at `PENDING`, per `Booking`'s own docstring)
        and holds its listing. If a booking with the same `(session_id, idempotency_key)`
        already exists, returns *that* one unchanged instead of inserting a second row --
        gate 8.5's "two identical responses" starts here, at the storage boundary, not just
        in the tool handler's own branching.
        """
        ...

    async def update(self, booking: Booking) -> None:
        """Persists a booking that has moved to a new state. Releases the listing hold when
        the new state is terminal.
        """
        ...

    async def get(self, booking_id: uuid.UUID) -> Booking | None: ...

    async def pending_since(self) -> tuple[tuple[uuid.UUID, datetime], ...]:
        """`(id, pending_since)` for every currently-`PENDING` booking -- what
        `expire_stale` sweeps."""
        ...

    def is_held(self, listing_id: uuid.UUID) -> bool: ...

    async def expire_stale(
        self, *, ttl_minutes: int = PENDING_TTL_MINUTES, now: datetime | None = None
    ) -> tuple[Booking, ...]:
        """Applies `BookingEvent.EXPIRE` to every `PENDING` booking older than the TTL and
        releases each one's listing hold. Returns the bookings that were expired, so a
        caller (a scheduled sweep, or a gate) can show its work.
        """
        ...


class InMemoryBookingStore:
    """The whole booking table in a dict. Used by tests and by `DEMO_MODE`."""

    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, Booking] = {}
        self._by_idem: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
        self._pending_since: dict[uuid.UUID, datetime] = {}
        self._held_listings: set[uuid.UUID] = set()

    async def find_by_idempotency_key(
        self, session_id: uuid.UUID, idempotency_key: str
    ) -> Booking | None:
        booking_id = self._by_idem.get((session_id, idempotency_key))
        return self._by_id.get(booking_id) if booking_id is not None else None

    async def insert(self, booking: Booking) -> Booking:
        # No `await` between the check and the write below -- this coroutine never yields
        # the event loop mid-operation, so a concurrent `insert` for the same idempotency
        # key cannot interleave with it (see this module's docstring).
        existing = await self.find_by_idempotency_key(booking.session_id, booking.idempotency_key)
        if existing is not None:
            return existing

        self._by_id[booking.id] = booking
        self._by_idem[(booking.session_id, booking.idempotency_key)] = booking.id
        if booking.state is BookingState.PENDING:
            self._pending_since[booking.id] = booking.created_at
            self._held_listings.add(booking.listing_id)
        return booking

    async def update(self, booking: Booking) -> None:
        self._by_id[booking.id] = booking
        if booking.state is BookingState.PENDING:
            self._pending_since.setdefault(booking.id, booking.updated_at)
        else:
            self._pending_since.pop(booking.id, None)
            self._held_listings.discard(booking.listing_id)

    async def get(self, booking_id: uuid.UUID) -> Booking | None:
        return self._by_id.get(booking_id)

    async def pending_since(self) -> tuple[tuple[uuid.UUID, datetime], ...]:
        return tuple(self._pending_since.items())

    def is_held(self, listing_id: uuid.UUID) -> bool:
        return listing_id in self._held_listings

    async def expire_stale(
        self, *, ttl_minutes: int = PENDING_TTL_MINUTES, now: datetime | None = None
    ) -> tuple[Booking, ...]:
        return await expire_stale_bookings(self, ttl_minutes=ttl_minutes, now=now)


async def expire_stale_bookings(
    store: BookingStore, *, ttl_minutes: int, now: datetime | None
) -> tuple[Booking, ...]:
    """Shared between every `BookingStore` implementation: read the candidates, decide which
    are stale with the pure domain function, apply the transition, persist. Not itself a
    protocol method's default -- `Protocol` doesn't support one -- so both implementations
    call through this rather than each re-deriving the same sweep loop.
    """
    effective_now = now if now is not None else datetime.now(UTC)
    pending = await store.pending_since()
    to_expire = stale_pending(pending, now=effective_now, ttl_minutes=ttl_minutes)
    expired: list[Booking] = []
    for booking_id in to_expire:
        booking = await store.get(booking_id)
        if booking is None or booking.state is not BookingState.PENDING:
            continue
        entry = new_audit_entry(
            actor="system",
            from_state=BookingState.PENDING,
            event=BookingEvent.EXPIRE,
            event_id=f"sweep:{effective_now.isoformat()}",
            now=effective_now,
            note=f"PENDING for longer than the {ttl_minutes}-minute TTL",
        )
        updated = booking.with_transition(entry, now=effective_now)
        await store.update(updated)
        expired.append(updated)
    return tuple(expired)
