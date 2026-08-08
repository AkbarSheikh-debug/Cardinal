"""Booking contracts and the booking lifecycle state machine (PHASE-8 §3).

`BookingDraft` and `Booking` are separate types on purpose (PHASE-0 §4). A draft has no row
in the bookings table; promoting one is an explicit, audited transition. Making them one
type with a nullable id is how a draft accidentally becomes a confirmed booking.

CONSTITUTION I.2 lives in P8, not here: no code in this module can confirm anything. What
*does* live here is the state machine every confirmation has to pass through -- `apply_transition`
is a pure function of `(state, event)`, so gate 8.1's exhaustiveness check ("every pair either
transitions or explicitly rejects") is checkable with no fixture, no clock and no I/O.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.dates import DateRange
from src.domain.money import Money

__all__ = [
    "TRANSITIONS",
    "Actor",
    "Booking",
    "BookingAuditEntry",
    "BookingDraft",
    "BookingEvent",
    "BookingState",
    "Customer",
    "DateRange",
    "InvalidTransitionError",
    "apply_transition",
    "is_terminal",
    "new_audit_entry",
    "stale_pending",
]


class BookingState(StrEnum):
    """Seven states, not six. PHASE-8 §3's own diagram draws six boxes (DRAFT, PENDING,
    CONFIRMED, FAILED, CANCELLED, ABANDONED) but its prose promises a seventh: "PENDING has a
    TTL... 15 minutes, then EXPIRED, then the listing is released" -- and gate 8.9 tests
    exactly that transition by name. Treated as the doc undercounting in the summary line
    rather than EXPIRED secretly meaning CANCELLED; see DECISIONS.md D-035.
    """

    DRAFT = "draft"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


class BookingEvent(StrEnum):
    """The only things that ever move a booking. Six states x six events = 36 pairs; the
    six below are the legal ones, `TRANSITIONS` is the whole truth, and `apply_transition`
    raises `InvalidTransitionError` -- never a silent no-op -- for every other pair.
    """

    SUBMIT = "submit"
    ABANDON = "abandon"
    AUTHORISE = "authorise"
    DECLINE = "decline"
    EXPIRE = "expire"
    CANCEL = "cancel"


class InvalidTransitionError(ValueError):
    def __init__(self, state: BookingState, event: BookingEvent) -> None:
        super().__init__(f"{event.value!r} is not a valid transition from {state.value!r}")
        self.state = state
        self.event = event


#: The entire state machine (PHASE-8 §3's diagram, read literally). No transition exists
#: outside this table -- `apply_transition` is the only place that reads it, and gate 8.1
#: asserts every `(state, event)` pair not listed here raises.
TRANSITIONS: dict[tuple[BookingState, BookingEvent], BookingState] = {
    (BookingState.DRAFT, BookingEvent.SUBMIT): BookingState.PENDING,
    (BookingState.DRAFT, BookingEvent.ABANDON): BookingState.ABANDONED,
    (BookingState.PENDING, BookingEvent.AUTHORISE): BookingState.CONFIRMED,
    (BookingState.PENDING, BookingEvent.DECLINE): BookingState.FAILED,
    (BookingState.PENDING, BookingEvent.EXPIRE): BookingState.EXPIRED,
    (BookingState.CONFIRMED, BookingEvent.CANCEL): BookingState.CANCELLED,
}

#: States with zero outgoing edges in `TRANSITIONS` -- `apply_transition` rejects every event
#: from one of these by construction, which is what "terminal" means here. `CONFIRMED` is
#: deliberately *not* in this set: PHASE-8 §3's diagram gives it exactly one live edge
#: (`cancel` -> `CANCELLED`), so a confirmed booking is a settled outcome, not a dead end.
_TERMINAL: frozenset[BookingState] = frozenset(
    {
        BookingState.FAILED,
        BookingState.CANCELLED,
        BookingState.ABANDONED,
        BookingState.EXPIRED,
    }
)


def is_terminal(state: BookingState) -> bool:
    return state in _TERMINAL


def apply_transition(state: BookingState, event: BookingEvent) -> BookingState:
    """The one function that may ever change a `Booking.state`. Raises rather than returning
    the input state unchanged on an illegal pair -- gate 8.1's "no silent no-ops."
    """
    key = (state, event)
    if key not in TRANSITIONS:
        raise InvalidTransitionError(state, event)
    return TRANSITIONS[key]


Actor = Literal["user", "agent", "system"]


class BookingAuditEntry(BaseModel):
    """One line of the append-only trail (PHASE-8 §3): actor, timestamp, from-state,
    to-state, and the event that triggered the move. `event_id` ties a row back to whatever
    caused it -- an idempotency key for a user-triggered submit, a gateway auth id for a
    system-triggered authorise/decline, a sweep run id for an expiry.
    """

    model_config = ConfigDict(frozen=True)

    actor: Actor
    timestamp: datetime
    from_state: BookingState
    to_state: BookingState
    event: BookingEvent
    event_id: str
    note: str = ""


def new_audit_entry(
    *,
    actor: Actor,
    from_state: BookingState,
    event: BookingEvent,
    event_id: str,
    now: datetime,
    note: str = "",
) -> BookingAuditEntry:
    """Applies the transition and builds its audit row together, so the two can never drift
    apart (an audit entry whose `to_state` doesn't match what `apply_transition` actually
    produced would be worse than no audit trail at all).
    """
    to_state = apply_transition(from_state, event)
    return BookingAuditEntry(
        actor=actor,
        timestamp=now,
        from_state=from_state,
        to_state=to_state,
        event=event,
        event_id=event_id,
        note=note,
    )


class Customer(BaseModel):
    model_config = ConfigDict(frozen=True)

    full_name: str = Field(min_length=1)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = None
    licence_number: str | None = None


class BookingDraft(BaseModel):
    """Prepared, pre-filled, and shown to the user. Never confirmed."""

    model_config = ConfigDict(frozen=True)

    session_id: uuid.UUID
    listing_id: uuid.UUID
    customer: Customer
    window: DateRange | None = Field(default=None, description="Required for a rental.")
    total: Money
    idempotency_key: str = Field(min_length=8)


class Booking(BaseModel):
    """A draft that a human explicitly confirmed. Only P8 may construct one.

    Springs into existence already at `PENDING` -- there is no row while it is a `DRAFT`
    (PHASE-8 §3) -- with `audit[0]` recording the DRAFT->PENDING promotion that created it.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: uuid.UUID
    session_id: uuid.UUID
    listing_id: uuid.UUID
    state: BookingState
    customer: Customer
    window: DateRange | None = None
    total: Money
    idempotency_key: str = Field(min_length=8)
    audit: tuple[BookingAuditEntry, ...] = Field(
        default=(), description="Append-only transition log. Never rewritten in place."
    )
    created_at: datetime
    updated_at: datetime

    def with_transition(self, entry: BookingAuditEntry, *, now: datetime) -> Booking:
        """Returns a new `Booking` reflecting one more audit entry. Does not itself call
        `apply_transition` -- `entry.to_state` is trusted because `new_audit_entry` is the
        only place that produces one, and re-deriving it here would just be the same check
        twice for no extra safety.
        """
        if entry.from_state != self.state:
            raise InvalidTransitionError(self.state, entry.event)
        return self.model_copy(
            update={
                "state": entry.to_state,
                "audit": (*self.audit, entry),
                "updated_at": now,
            }
        )


def stale_pending(
    pending: tuple[tuple[uuid.UUID, datetime], ...], *, now: datetime, ttl_minutes: int
) -> tuple[uuid.UUID, ...]:
    """Which `PENDING` bookings are older than the TTL (PHASE-8 §3: "15 minutes, then
    EXPIRED"), given as `(id, pending_since)` pairs. Pure -- `now` is a parameter, never
    `datetime.now()`, so this stays callable from a property test with no clock at all. The
    caller (an adapter, which is allowed to touch the clock and the database) is what
    actually applies `BookingEvent.EXPIRE` to each id this returns.
    """
    cutoff_seconds = ttl_minutes * 60
    return tuple(
        booking_id
        for booking_id, pending_since in pending
        if (now - pending_since).total_seconds() >= cutoff_seconds
    )
