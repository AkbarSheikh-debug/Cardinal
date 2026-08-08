"""Gate 8.5/8.9's durable sibling: `PostgresBookingStore` reuses the `bookings` table
extended in `migrations/0002_bookings_commerce`. `session_id`/`listing_id` carry real foreign
keys (`sessions.id` ON DELETE CASCADE, `listings.id`), so every test here seeds a bare
`SessionRow` and `ListingRow` first, the same precondition
`test_agent_journal_postgres.py` already establishes for `decisions.session_id`.

Skipped when `CARDINAL_DATABASE_URL` is unset, same convention as every other
`tests/integration/test_*_postgres.py` module.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from src.adapters.catalogue.generator import generate_catalogue
from src.adapters.db.booking_store import PostgresBookingStore
from src.adapters.db.mapping import to_row
from src.adapters.db.models import ListingRow, SessionRow
from src.adapters.db.session import dispose_engine, session_factory
from src.domain.booking import Booking, BookingEvent, BookingState, Customer, new_audit_entry
from src.domain.money import Money

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
async def _cleanup_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()


async def _ensure_session_row(session_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    async with session_factory()() as session:
        session.add(
            SessionRow(
                id=session_id,
                user_id="booking-store-test",
                phase="transact",
                profile={},
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


async def _ensure_listing_row() -> uuid.UUID:
    listing = generate_catalogue()[0]
    async with session_factory()() as session:
        existing = await session.get(ListingRow, listing.id)
        if existing is None:
            session.add(to_row(listing))
            await session.commit()
    return listing.id


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


async def test_insert_round_trips_through_a_fresh_store_instance(database_url_or_skip: str) -> None:
    session_id = uuid.uuid4()
    await _ensure_session_row(session_id)
    listing_id = await _ensure_listing_row()
    now = datetime.now(UTC)
    booking = _fresh_booking(
        session_id=session_id, listing_id=listing_id, idem="pg-idem-1", now=now
    )

    writer = PostgresBookingStore(session_factory())
    await writer.insert(booking)

    reader = PostgresBookingStore(session_factory())
    found = await reader.find_by_idempotency_key(session_id, "pg-idem-1")
    assert found is not None
    assert found.id == booking.id
    assert found.state is BookingState.PENDING
    assert found.audit == booking.audit


async def test_repeated_insert_with_the_same_idempotency_key_does_not_duplicate(
    database_url_or_skip: str,
) -> None:
    session_id = uuid.uuid4()
    await _ensure_session_row(session_id)
    listing_id = await _ensure_listing_row()
    now = datetime.now(UTC)
    first = _fresh_booking(session_id=session_id, listing_id=listing_id, idem="pg-idem-2", now=now)
    second = _fresh_booking(session_id=session_id, listing_id=listing_id, idem="pg-idem-2", now=now)

    store = PostgresBookingStore(session_factory())
    inserted_first = await store.insert(first)
    inserted_second = await store.insert(second)

    assert inserted_first.id == inserted_second.id == first.id
    assert await store.get(second.id) is None


async def test_update_persists_a_transition_and_expire_stale_finds_it(
    database_url_or_skip: str,
) -> None:
    session_id = uuid.uuid4()
    await _ensure_session_row(session_id)
    listing_id = await _ensure_listing_row()
    stale_time = datetime.now(UTC) - timedelta(hours=1)
    store = PostgresBookingStore(session_factory())
    await store.insert(
        _fresh_booking(
            session_id=session_id, listing_id=listing_id, idem="pg-idem-3", now=stale_time
        )
    )

    expired = await store.expire_stale(now=datetime.now(UTC))
    assert any(b.idempotency_key == "pg-idem-3" for b in expired)

    reader = PostgresBookingStore(session_factory())
    found = await reader.find_by_idempotency_key(session_id, "pg-idem-3")
    assert found is not None
    assert found.state is BookingState.EXPIRED
    assert found.audit[-1].event is BookingEvent.EXPIRE
