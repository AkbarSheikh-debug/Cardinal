"""`src/adapters/lead_store.py` -- PLAN-02 P15.

Two properties, and both are about the interface rather than the implementation: a repeated
action updates one lead instead of creating a second (gate 15.1), and there is no way to
phrase "give me every lead" so cross-dealer leakage (gate 15.5) is not a filter that could be
forgotten.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.adapters.lead_store import InMemoryLeadStore
from src.domain.lead import IntentTier, LeadEvent, LeadScore, LeadSignal, LeadState, lead_uuid

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
BUYER = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_BUYER = uuid.UUID("aaaaaaaa-1111-1111-1111-111111111111")
DEALER = uuid.UUID("22222222-2222-2222-2222-222222222222")
OTHER_DEALER = uuid.UUID("bbbbbbbb-2222-2222-2222-222222222222")
LISTING = uuid.UUID("33333333-3333-3333-3333-333333333333")
OTHER_LISTING = uuid.UUID("cccccccc-3333-3333-3333-333333333333")


def scorer(events: tuple[LeadEvent, ...]) -> LeadScore:
    """A stand-in for `score_lead` that rises with the number of events, so a test can see
    that re-scoring actually happened without depending on the real weights."""
    weight = min(1.0, 0.2 * len(events))
    signal = LeadSignal(
        name="added_to_cart",
        value=1.0,
        weight=weight,
        contribution=weight,
        explanation=f"{len(events)} action(s)",
    )
    tier = IntentTier.HIGH if weight >= 0.6 else IntentTier.LOW
    return LeadScore(tier=tier, score=weight, signals=(signal,), explanation=tier.label)


async def record(
    store: InMemoryLeadStore,
    *,
    buyer: uuid.UUID = BUYER,
    dealer: uuid.UUID = DEALER,
    listing: uuid.UUID = LISTING,
    event: LeadEvent = LeadEvent.CART_ADD,
    summary: str = "Buying · suv",
    now: datetime = NOW,
):
    return await store.record_event(
        buyer_account_id=buyer,
        dealer_id=dealer,
        listing_id=listing,
        source="mock_autobazaar",
        source_id="AB-1073",
        requirement_summary=summary,
        event=event,
        score_with=scorer,
        now=now,
    )


# -- one lead per buyer per car (gate 15.1) -----------------------------------------


async def test_a_first_action_creates_a_lead() -> None:
    store = InMemoryLeadStore()
    lead, is_new = await record(store)

    assert is_new
    assert lead.id == lead_uuid(BUYER, LISTING)
    assert lead.events == (LeadEvent.CART_ADD,)
    assert len(await store.for_dealer(DEALER)) == 1


async def test_a_second_action_on_the_same_car_updates_the_same_lead() -> None:
    store = InMemoryLeadStore()
    first, _ = await record(store)
    second, is_new = await record(
        store, event=LeadEvent.CHECKOUT_OPENED, now=NOW + timedelta(hours=1)
    )

    assert not is_new
    assert second.id == first.id
    assert second.events == (LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED)
    assert len(await store.for_dealer(DEALER)) == 1


async def test_accumulated_events_are_what_gets_rescored() -> None:
    """`score_with` receives the whole event set, not the one event that just happened -- a
    lead whose tier reflected only the latest action would demote itself on a re-click."""
    store = InMemoryLeadStore()
    await record(store)
    await record(store, event=LeadEvent.CHECKOUT_OPENED)
    lead, _ = await record(store, event=LeadEvent.BOOKING_SUBMITTED)

    assert lead.score.tier is IntentTier.HIGH
    assert "3 action(s)" in lead.score.signals[0].explanation


async def test_repeating_the_same_action_does_not_duplicate_the_event() -> None:
    store = InMemoryLeadStore()
    await record(store)
    lead, is_new = await record(store)

    assert not is_new
    assert lead.events == (LeadEvent.CART_ADD,)


async def test_a_second_car_is_a_second_lead() -> None:
    store = InMemoryLeadStore()
    await record(store)
    await record(store, listing=OTHER_LISTING)

    assert len(await store.for_dealer(DEALER)) == 2


async def test_a_refreshed_requirement_summary_replaces_a_stale_one() -> None:
    """The interview keeps running after a cart-add. A lead still saying "no budget stated"
    once the buyer has stated one is stale in the field a salesperson reads first."""
    store = InMemoryLeadStore()
    await record(store, summary="Interview still in progress.")
    lead, _ = await record(
        store, event=LeadEvent.CHECKOUT_OPENED, summary="Buying · suv · budget EUR 30,000"
    )

    assert "30,000" in lead.requirement_summary


# -- dealer scoping (gate 15.5) -----------------------------------------------------


async def test_one_dealers_leads_are_invisible_to_another() -> None:
    store = InMemoryLeadStore()
    await record(store, dealer=DEALER)
    await record(store, dealer=OTHER_DEALER, listing=OTHER_LISTING)

    assert len(await store.for_dealer(DEALER)) == 1
    assert len(await store.for_dealer(OTHER_DEALER)) == 1


async def test_a_lead_id_is_not_a_capability() -> None:
    """Knowing another dealer's lead id gets a seller nothing: the lookup is scoped, so the
    id alone resolves to `None`."""
    store = InMemoryLeadStore()
    lead, _ = await record(store, dealer=DEALER)

    assert await store.get(DEALER, lead.id) is not None
    assert await store.get(OTHER_DEALER, lead.id) is None


async def test_marking_another_dealers_lead_contacted_does_nothing() -> None:
    store = InMemoryLeadStore()
    lead, _ = await record(store, dealer=DEALER)

    assert await store.set_state(OTHER_DEALER, lead.id, LeadState.CONTACTED) is None
    assert (await store.get(DEALER, lead.id)).state is LeadState.NEW  # type: ignore[union-attr]


async def test_two_buyers_on_one_dealers_car_are_two_leads() -> None:
    store = InMemoryLeadStore()
    await record(store, buyer=BUYER)
    await record(store, buyer=OTHER_BUYER)

    assert len(await store.for_dealer(DEALER)) == 2


# -- state ---------------------------------------------------------------------------


async def test_marking_contacted_persists() -> None:
    store = InMemoryLeadStore()
    lead, _ = await record(store)

    updated = await store.set_state(DEALER, lead.id, LeadState.CONTACTED)

    assert updated is not None and updated.state is LeadState.CONTACTED
    reloaded = await store.get(DEALER, lead.id)
    assert reloaded is not None and reloaded.state is LeadState.CONTACTED


async def test_setting_the_state_of_a_lead_that_does_not_exist_returns_none() -> None:
    assert await InMemoryLeadStore().set_state(DEALER, uuid.uuid4(), LeadState.CONTACTED) is None
