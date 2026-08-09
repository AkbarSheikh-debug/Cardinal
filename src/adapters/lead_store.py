"""Where leads live, behind an interface -- the protocol/in-memory/Postgres split every other
store in this package makes (PLAN-02 P15).

**Every read method takes a `dealer_id` and there is no method that returns all leads.** That
is what makes gate 15.5 ("seller A never sees seller B's leads") a property of the interface
rather than a filter a route has to remember to apply -- the same shape `CartStore` uses for
accounts, for the same reason (CONSTITUTION IV.4).

Writes go through `record_event`, which upserts on `(buyer_account_id, listing_id)` via
`lead_uuid`. A buyer who adds a car, opens checkout and submits a form produces **one** lead
that accumulates all three events and re-scores each time (gate 15.1) -- not three leads and
not a lead whose tier is frozen at whatever the first action implied.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from src.domain.lead import Lead, LeadEvent, LeadScore, LeadState, lead_uuid


class LeadStore(Protocol):
    async def for_dealer(self, dealer_id: uuid.UUID) -> tuple[Lead, ...]:
        """Newest-scoring-first is the *route's* business; this returns them in a stable
        order and lets the caller sort. Scoped to one dealer, always."""
        ...

    async def get(self, dealer_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        """Both ids, deliberately: a lead id alone is not a capability, so knowing another
        dealer's lead id gets a seller nothing (the shape `CartStore.remove` uses)."""
        ...

    async def record_event(
        self,
        *,
        buyer_account_id: uuid.UUID,
        dealer_id: uuid.UUID,
        listing_id: uuid.UUID,
        source: str,
        source_id: str,
        requirement_summary: str,
        event: LeadEvent,
        score_with: ScoreFn,
        now: datetime | None = None,
    ) -> tuple[Lead, bool]:
        """Upserts and returns `(lead, is_new)`.

        `score_with` is a callback rather than a `LeadScore`, because the score depends on the
        *accumulated* event set and only the store knows what that is after this write. A
        caller passing a pre-computed score would be scoring the event it just observed rather
        than everything this buyer has done with this car.
        """
        ...

    async def set_state(
        self,
        dealer_id: uuid.UUID,
        lead_id: uuid.UUID,
        state: LeadState,
        *,
        now: datetime | None = None,
    ) -> Lead | None: ...


class ScoreFn(Protocol):
    def __call__(self, events: tuple[LeadEvent, ...]) -> LeadScore: ...


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


class InMemoryLeadStore:
    """Every lead in a dict, keyed by its deterministic id. Tests, gates and `DEMO_MODE`."""

    def __init__(self) -> None:
        self._leads: dict[uuid.UUID, Lead] = {}

    async def for_dealer(self, dealer_id: uuid.UUID) -> tuple[Lead, ...]:
        return tuple(
            sorted(
                (lead for lead in self._leads.values() if lead.dealer_id == dealer_id),
                key=lambda lead: (lead.created_at, str(lead.id)),
            )
        )

    async def get(self, dealer_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        lead = self._leads.get(lead_id)
        return lead if lead is not None and lead.dealer_id == dealer_id else None

    async def record_event(
        self,
        *,
        buyer_account_id: uuid.UUID,
        dealer_id: uuid.UUID,
        listing_id: uuid.UUID,
        source: str,
        source_id: str,
        requirement_summary: str,
        event: LeadEvent,
        score_with: ScoreFn,
        now: datetime | None = None,
    ) -> tuple[Lead, bool]:
        moment = _now(now)
        lead_id = lead_uuid(buyer_account_id, listing_id)
        existing = self._leads.get(lead_id)

        if existing is None:
            lead = Lead(
                id=lead_id,
                buyer_account_id=buyer_account_id,
                dealer_id=dealer_id,
                listing_id=listing_id,
                source=source,
                source_id=source_id,
                requirement_summary=requirement_summary,
                events=(event,),
                score=score_with((event,)),
                created_at=moment,
                updated_at=moment,
            )
            self._leads[lead_id] = lead
            return lead, True

        events = existing.events if event in existing.events else (*existing.events, event)
        updated = existing.with_event(event, score=score_with(events), now=moment)
        # The summary is refreshed too: the interview keeps running after a cart-add, and a
        # lead still saying "budget not stated" once the buyer has stated one is stale in the
        # one field the dealer reads first.
        if requirement_summary and requirement_summary != updated.requirement_summary:
            updated = updated.model_copy(
                update={"requirement_summary": requirement_summary, "updated_at": moment}
            )
        self._leads[lead_id] = updated
        return updated, False

    async def set_state(
        self,
        dealer_id: uuid.UUID,
        lead_id: uuid.UUID,
        state: LeadState,
        *,
        now: datetime | None = None,
    ) -> Lead | None:
        lead = await self.get(dealer_id, lead_id)
        if lead is None:
            return None
        updated = lead.with_state(state, now=_now(now))
        self._leads[lead_id] = updated
        return updated
