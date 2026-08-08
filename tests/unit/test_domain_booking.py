"""Gate 8.1 lives here: the booking lifecycle state machine is exhaustive over every
`(state, event)` pair -- each one either transitions or explicitly rejects, never a silent
no-op. Plus the audit-entry/`Booking.with_transition` machinery gate 8.12 relies on, and the
pure TTL predicate gate 8.9's sweep is built from.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domain.booking import (
    TRANSITIONS,
    Booking,
    BookingEvent,
    BookingState,
    Customer,
    InvalidTransitionError,
    apply_transition,
    is_terminal,
    new_audit_entry,
    stale_pending,
)
from src.domain.money import Money


def test_gate_8_1_every_state_event_pair_transitions_or_explicitly_rejects() -> None:
    """The literal criterion: no `(state, event)` pair is a silent no-op. Every pair either
    appears in `TRANSITIONS` and `apply_transition` returns exactly that, or it isn't there
    and `apply_transition` raises -- there is no third outcome.
    """
    checked = 0
    for state, event in itertools.product(BookingState, BookingEvent):
        checked += 1
        if (state, event) in TRANSITIONS:
            result = apply_transition(state, event)
            assert result == TRANSITIONS[(state, event)]
        else:
            with pytest.raises(InvalidTransitionError):
                apply_transition(state, event)
    assert checked == len(BookingState) * len(BookingEvent) == 42


def test_the_six_documented_transitions_are_exactly_these_six() -> None:
    """Pins PHASE-8 §3's diagram literally, so a future edit to `TRANSITIONS` that adds or
    drops one has to change this test too, not just quietly pass gate 8.1's generic scan.
    """
    assert TRANSITIONS == {
        (BookingState.DRAFT, BookingEvent.SUBMIT): BookingState.PENDING,
        (BookingState.DRAFT, BookingEvent.ABANDON): BookingState.ABANDONED,
        (BookingState.PENDING, BookingEvent.AUTHORISE): BookingState.CONFIRMED,
        (BookingState.PENDING, BookingEvent.DECLINE): BookingState.FAILED,
        (BookingState.PENDING, BookingEvent.EXPIRE): BookingState.EXPIRED,
        (BookingState.CONFIRMED, BookingEvent.CANCEL): BookingState.CANCELLED,
    }


def test_every_terminal_state_rejects_every_event() -> None:
    terminal = (
        BookingState.FAILED,
        BookingState.CANCELLED,
        BookingState.ABANDONED,
        BookingState.EXPIRED,
    )
    for state in terminal:
        assert is_terminal(state)
        for event in BookingEvent:
            with pytest.raises(InvalidTransitionError):
                apply_transition(state, event)


def test_confirmed_is_not_terminal_it_has_exactly_one_live_edge_to_cancelled() -> None:
    """PHASE-8 §3's diagram draws `CONFIRMED --cancel--> CANCELLED` -- a settled purchase can
    still be cancelled, so `CONFIRMED` is not a dead end the way `FAILED`/`EXPIRED` are.
    """
    assert not is_terminal(BookingState.CONFIRMED)
    assert apply_transition(BookingState.CONFIRMED, BookingEvent.CANCEL) is BookingState.CANCELLED
    for event in BookingEvent:
        if event is BookingEvent.CANCEL:
            continue
        with pytest.raises(InvalidTransitionError):
            apply_transition(BookingState.CONFIRMED, event)


def test_draft_and_pending_are_not_terminal() -> None:
    assert not is_terminal(BookingState.DRAFT)
    assert not is_terminal(BookingState.PENDING)


def test_new_audit_entry_applies_the_transition_and_records_it() -> None:
    now = datetime(2026, 8, 8, tzinfo=UTC)
    entry = new_audit_entry(
        actor="user",
        from_state=BookingState.DRAFT,
        event=BookingEvent.SUBMIT,
        event_id="idem-1",
        now=now,
        note="checkout confirmed by a trusted click",
    )
    assert entry.from_state is BookingState.DRAFT
    assert entry.to_state is BookingState.PENDING
    assert entry.actor == "user"
    assert entry.timestamp == now
    assert entry.event_id == "idem-1"


def test_new_audit_entry_raises_on_an_illegal_transition() -> None:
    with pytest.raises(InvalidTransitionError):
        new_audit_entry(
            actor="system",
            from_state=BookingState.CONFIRMED,
            event=BookingEvent.SUBMIT,
            event_id="x",
            now=datetime.now(UTC),
        )


def _booking(state: BookingState, *, now: datetime) -> Booking:
    return Booking(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        listing_id=uuid.uuid4(),
        state=state,
        customer=Customer(full_name="Jane Doe", email="jane@example.com"),
        total=Money.of("20000"),
        idempotency_key="idem-00000001",
        audit=(),
        created_at=now,
        updated_at=now,
    )


def test_booking_with_transition_moves_state_and_appends_the_audit_entry() -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    booking = _booking(BookingState.PENDING, now=now)
    later = now + timedelta(seconds=2)
    entry = new_audit_entry(
        actor="system",
        from_state=BookingState.PENDING,
        event=BookingEvent.AUTHORISE,
        event_id="auth-1",
        now=later,
    )
    updated = booking.with_transition(entry, now=later)
    assert updated.state is BookingState.CONFIRMED
    assert updated.audit == (entry,)
    assert updated.updated_at == later
    # The original is untouched -- `Booking` fields are mutable, but `with_transition`
    # returns a copy rather than mutating in place.
    assert booking.state is BookingState.PENDING
    assert booking.audit == ()


def test_booking_with_transition_rejects_an_entry_for_the_wrong_state() -> None:
    now = datetime.now(UTC)
    booking = _booking(BookingState.DRAFT, now=now)
    entry = new_audit_entry(
        actor="system",
        from_state=BookingState.PENDING,  # booking is actually DRAFT
        event=BookingEvent.AUTHORISE,
        event_id="auth-1",
        now=now,
    )
    with pytest.raises(InvalidTransitionError):
        booking.with_transition(entry, now=now)


def test_stale_pending_is_a_pure_function_of_now_and_ttl() -> None:
    booking_id = uuid.uuid4()
    pending_since = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)

    # Exactly at the TTL boundary: stale (">=" per the domain function).
    at_boundary = pending_since + timedelta(minutes=15)
    assert stale_pending(((booking_id, pending_since),), now=at_boundary, ttl_minutes=15) == (
        booking_id,
    )

    # One second before the boundary: not yet stale.
    before_boundary = pending_since + timedelta(minutes=15) - timedelta(seconds=1)
    assert stale_pending(((booking_id, pending_since),), now=before_boundary, ttl_minutes=15) == ()


def test_stale_pending_only_returns_the_stale_ids_from_a_mixed_batch() -> None:
    now = datetime(2026, 8, 8, 13, 0, tzinfo=UTC)
    fresh_id, stale_id = uuid.uuid4(), uuid.uuid4()
    pending = (
        (fresh_id, now - timedelta(minutes=1)),
        (stale_id, now - timedelta(minutes=20)),
    )
    assert stale_pending(pending, now=now, ttl_minutes=15) == (stale_id,)
