"""Leads -- the seller-facing half of the marketplace (PLAN-02 P15).

A lead is what a dealership would actually pay for: a named buyer, the car they engaged with,
what they asked for, and an estimate of how urgently to call them, with the reasoning attached.

Three rules are baked into these types rather than left to the routes that use them:

- **A lead only exists after an intent action.** There is no constructor for "someone looked
  at your car": `Lead` requires at least one `LeadEvent`, and the three events that exist are
  all deliberate acts. Browsing produces nothing, so a seller can never be shown the contact
  details of someone who merely passed through (PLAN-02 P15's privacy rule, gate 15.6).
- **The tier is computed, never asserted.** `IntentTier.label` phrases every tier as an
  estimate and `LeadScore` carries the named signals that produced it, the same shape P5's
  `ScoreBreakdown` uses for listing rank and for the same reason (PLAN-02 §0.5): a dealer who
  cannot see *why* a lead scored High stops trusting the tier within a week.
- **Nothing here knows what a buyer earns.** See `src/domain/lead_scoring.py`'s docstring for
  why income is not an input at all, which is a departure from PLAN-02 §P15's signal table
  and the only way both of that section's own rules can hold at once (D-079).

Pure: no db, no clock, no network (CONSTITUTION II.1). Every `now` is passed in.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Stable namespace so `lead_uuid(buyer, listing)` is reproducible across processes -- the
#: same trick `listing_uuid`/`dealer_uuid` use, and what makes "one lead per buyer per car"
#: (gate 15.1) a property of the id rather than of a uniqueness check someone remembers.
LEAD_NAMESPACE = uuid.UUID("6f2d1a4c-9b7e-4c31-8a55-2e0d7b4c1f93")


def lead_uuid(buyer_account_id: uuid.UUID, listing_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(LEAD_NAMESPACE, f"{buyer_account_id}:{listing_id}")


class LeadEvent(StrEnum):
    """The buyer actions that qualify. All three are deliberate; none of them is browsing.

    Ordered by what they say about intent, which is also the order `lead_scoring` weights
    them: opening checkout is the strongest thing short of confirming.
    """

    CART_ADD = "cart_add"
    BOOKING_SUBMITTED = "booking_submitted"
    CHECKOUT_OPENED = "checkout_opened"


class LeadState(StrEnum):
    NEW = "new"
    VIEWED = "viewed"
    CONTACTED = "contacted"
    CLOSED = "closed"


class IntentTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def label(self) -> str:
        """Always an estimate, never an assertion about a person (gate 15.8).

        "High purchase intent" states a fact about someone's mind that nobody here knows.
        "High purchase intent (estimated)" states what this actually is: a number computed
        from seven observable signals, all of which are shown next to it.
        """
        return f"{self.name.capitalize()} purchase intent (estimated)"

    @property
    def guidance(self) -> str:
        """What PLAN-02 §P15's tier table tells the dealer to do. Phrased as a suggested
        cadence, because it is one -- the dealer's own process wins."""
        return {
            IntentTier.HIGH: "Likely buying within a few days — call now.",
            IntentTier.MEDIUM: "Likely buying within a week or two — call within a day or two.",
            IntentTier.LOW: "Gathering information — follow your own cadence.",
        }[self]


#: Tier -> how long the dealer has before the lead goes cold, surfaced as a countdown.
#: `None` for LOW on purpose: inventing a deadline for a buyer who is three months out would
#: manufacture urgency the signals do not support, and a countdown nobody believes trains
#: people to ignore the ones that matter.
SLA_WINDOWS: dict[IntentTier, timedelta | None] = {
    IntentTier.HIGH: timedelta(hours=2),
    IntentTier.MEDIUM: timedelta(hours=48),
    IntentTier.LOW: None,
}


def sla_deadline(tier: IntentTier, created_at: datetime) -> datetime | None:
    window = SLA_WINDOWS[tier]
    return created_at + window if window is not None else None


class LeadSignal(BaseModel):
    """One named input to a lead's score -- `CriterionScore`'s shape (`src/domain/scoring.py`),
    deliberately, so the "why this tier" panel and P6's score breakdown read the same way.

    `explanation` is the part `CriterionScore` has no equivalent of, and it earns its place:
    a dealer reading `target_date_proximity 0.28` learns nothing, while "target date is 5 days
    out" is a sentence they can act on and disbelieve.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    contribution: float
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _contribution_is_the_product(self) -> Self:
        if abs(self.contribution - self.weight * self.value) > 1e-9:
            raise ValueError("contribution must equal weight x value")
        return self


class LeadScore(BaseModel):
    """The tier, the number behind it, and every signal that produced it.

    The sum check is the same one `ScoreBreakdown` enforces (gate 5.2's shape, asserted again
    for leads by gate 15.3) and it is what makes the seller-facing panel honest: there is no
    hidden term, so the contributions on screen *are* the score, not a selection from it.
    """

    model_config = ConfigDict(frozen=True)

    tier: IntentTier
    score: float = Field(ge=0.0, le=1.0)
    signals: tuple[LeadSignal, ...]
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _score_is_the_sum(self) -> Self:
        if abs(self.score - sum(s.contribution for s in self.signals)) > 1e-9:
            raise ValueError("score must equal the sum of signal contributions")
        return self

    @property
    def ranked_signals(self) -> tuple[LeadSignal, ...]:
        """Biggest contributor first -- what the "why this tier" panel lists, and the order a
        dealer scanning it would want. Ties break on name so the order is deterministic."""
        return tuple(sorted(self.signals, key=lambda s: (-s.contribution, s.name)))


class Lead(BaseModel):
    """One buyer's engagement with one car, routed to the dealer who owns it.

    Identified by `(buyer_account_id, listing_id)` through `lead_uuid`, so a buyer who adds a
    car, opens checkout and submits a form produces **one** lead that accumulates events --
    not three (gate 15.1). Two different cars from the same dealer are two leads, which is
    right: they are two conversations to have.
    """

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    buyer_account_id: uuid.UUID
    dealer_id: uuid.UUID
    listing_id: uuid.UUID
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    #: What the buyer told the interview they wanted, in one line. Never carries income --
    #: `RequirementProfile` has no such field, which is the containment working as designed.
    requirement_summary: str
    events: tuple[LeadEvent, ...] = Field(min_length=1)
    score: LeadScore
    state: LeadState = LeadState.NEW
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _events_are_unique_and_ordered(self) -> Self:
        """A lead records *which* actions happened, not how many times. Storing `cart_add`
        twice would make a double-clicked button look like twice the intent, which is exactly
        the kind of thing that quietly inflates a tier."""
        if len(set(self.events)) != len(self.events):
            raise ValueError("events must be unique -- a lead records which, not how many")
        return self

    @property
    def sla_deadline(self) -> datetime | None:
        return sla_deadline(self.score.tier, self.created_at)

    def is_overdue(self, now: datetime) -> bool:
        deadline = self.sla_deadline
        return deadline is not None and now > deadline and self.state is LeadState.NEW

    def with_event(self, event: LeadEvent, *, score: LeadScore, now: datetime) -> Self:
        """Records an action and re-scores. Returns `self` unchanged when nothing moved, so a
        repeated action is not a spurious `updated_at` bump the seller's list re-sorts on."""
        if event in self.events and score == self.score:
            return self
        events = self.events if event in self.events else (*self.events, event)
        return self.model_copy(update={"events": events, "score": score, "updated_at": now})

    def with_state(self, state: LeadState, *, now: datetime) -> Self:
        if state is self.state:
            return self
        return self.model_copy(update={"state": state, "updated_at": now})
