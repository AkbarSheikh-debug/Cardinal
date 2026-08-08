"""`InMemoryBookingStore` (PHASE-8 §3/§6): idempotency, the listing hold, and the TTL sweep.
`PostgresBookingStore` is exercised by `tests/integration/test_adapters_booking_store_postgres.py`
against a real container -- the same in-memory/Postgres split every other store in this
codebase uses, and the same reason: this suite runs with no container at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.adapters.booking_store import (
    PENDING_TTL_MINUTES,
    InMemoryBookingStore,
    session_ref_to_uuid,
)
from src.domain.booking import Booking, BookingEvent, BookingState, Customer, new_audit_entry
from src.domain.money import Money


def _fresh_booking(
    *, session_id: uuid.UUID, listing_id: uuid.UUID, idem: str, now: datetime
) -> Booking:
    entry = new_audit_entry(
        actor="user",
        from_state=BookingState.DRAFT,
        event=BookingEvent.SUBMIT,
        event_id=idem,
        now=now,
    )
    return Booking(
        id=uuid.uuid4(),
        session_id=session_id,
        listing_id=listing_id,
        state=entry.to_state,
        customer=Customer(full_name="Jane Doe", email="jane@example.com"),
        total=Money.of("20000"),
        idempotency_key=idem,
        audit=(entry,),
        created_at=now,
        updated_at=now,
    )


async def test_insert_then_find_by_idempotency_key() -> None:
    store = InMemoryBookingStore()
    session_id, listing_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    booking = _fresh_booking(
        session_id=session_id, listing_id=listing_id, idem="idem-00000001", now=now
    )

    inserted = await store.insert(booking)
    assert inserted == booking

    found = await store.find_by_idempotency_key(session_id, "idem-00000001")
    assert found == booking
    assert await store.find_by_idempotency_key(session_id, "idem-does-not-exist") is None


async def test_insert_with_a_repeated_idempotency_key_returns_the_original() -> None:
    """Gate 8.5's storage-layer half: two inserts, same `(session_id, idempotency_key)`, one
    surviving row -- the second insert is a no-op that hands back the first booking.
    """
    store = InMemoryBookingStore()
    session_id, listing_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    first = _fresh_booking(
        session_id=session_id, listing_id=listing_id, idem="idem-00000002", now=now
    )
    second = _fresh_booking(
        session_id=session_id, listing_id=listing_id, idem="idem-00000002", now=now
    )
    assert first.id != second.id  # two distinct objects, same idempotency key

    await store.insert(first)
    result = await store.insert(second)
    assert result == first
    assert await store.get(second.id) is None  # the second one was never actually stored


async def test_insert_holds_the_listing_and_terminal_update_releases_it() -> None:
    store = InMemoryBookingStore()
    session_id, listing_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    booking = await store.insert(
        _fresh_booking(session_id=session_id, listing_id=listing_id, idem="idem-00000003", now=now)
    )
    assert store.is_held(listing_id)

    confirm_entry = new_audit_entry(
        actor="system",
        from_state=BookingState.PENDING,
        event=BookingEvent.AUTHORISE,
        event_id="auth-1",
        now=now,
    )
    confirmed = booking.with_transition(confirm_entry, now=now)
    await store.update(confirmed)
    assert not store.is_held(listing_id)


async def test_pending_since_only_reports_bookings_still_pending() -> None:
    store = InMemoryBookingStore()
    session_id = uuid.uuid4()
    now = datetime.now(UTC)
    still_pending = await store.insert(
        _fresh_booking(
            session_id=session_id, listing_id=uuid.uuid4(), idem="idem-pending1", now=now
        )
    )
    booking_to_confirm = await store.insert(
        _fresh_booking(
            session_id=session_id, listing_id=uuid.uuid4(), idem="idem-pending2", now=now
        )
    )
    entry = new_audit_entry(
        actor="system",
        from_state=BookingState.PENDING,
        event=BookingEvent.AUTHORISE,
        event_id="auth-2",
        now=now,
    )
    await store.update(booking_to_confirm.with_transition(entry, now=now))

    pending_ids = {booking_id for booking_id, _ in await store.pending_since()}
    assert pending_ids == {still_pending.id}


async def test_expire_stale_transitions_the_stale_booking_and_releases_its_hold() -> None:
    """Gate 8.9: a `PENDING` booking older than the TTL transitions to `EXPIRED` and its
    listing is released; a fresh one is untouched.
    """
    store = InMemoryBookingStore()
    session_id = uuid.uuid4()
    old_time = datetime.now(UTC) - timedelta(minutes=PENDING_TTL_MINUTES + 5)
    fresh_time = datetime.now(UTC)

    stale_listing_id = uuid.uuid4()
    stale = await store.insert(
        _fresh_booking(
            session_id=session_id, listing_id=stale_listing_id, idem="idem-stale", now=old_time
        )
    )
    fresh_listing_id = uuid.uuid4()
    fresh = await store.insert(
        _fresh_booking(
            session_id=session_id, listing_id=fresh_listing_id, idem="idem-fresh", now=fresh_time
        )
    )

    expired = await store.expire_stale(now=datetime.now(UTC))
    expired_ids = {booking.id for booking in expired}
    assert expired_ids == {stale.id}

    reloaded_stale = await store.get(stale.id)
    assert reloaded_stale is not None
    assert reloaded_stale.state is BookingState.EXPIRED
    assert reloaded_stale.audit[-1].event is BookingEvent.EXPIRE
    assert not store.is_held(stale_listing_id)

    reloaded_fresh = await store.get(fresh.id)
    assert reloaded_fresh is not None
    assert reloaded_fresh.state is BookingState.PENDING
    assert store.is_held(fresh_listing_id)


def test_session_ref_to_uuid_is_deterministic_for_a_non_uuid_session_id() -> None:
    assert session_ref_to_uuid("gate75") == session_ref_to_uuid("gate75")
    assert session_ref_to_uuid("gate75") != session_ref_to_uuid("gate76")


def test_session_ref_to_uuid_passes_through_a_real_uuid_string() -> None:
    real = uuid.uuid4()
    assert session_ref_to_uuid(str(real)) == real
