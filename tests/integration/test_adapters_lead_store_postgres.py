"""`PostgresLeadStore` -- PLAN-02 P15's durable path.

Every read goes through a **fresh store instance over a fresh sessionmaker**, the stand-in for
a process restart gates 3.2/4.1/12.5 already use.

The one thing that genuinely needs real SQL rather than the dict: the score breakdown has to
come back *as written*. `canonical` is the whole `Lead`, so a "why this tier" panel shows the
reasoning the lead was scored with -- not a recomputation against today's clock, which would
quietly disagree with the tier the moment a target date got closer.

Skipped when `CARDINAL_DATABASE_URL` is unset, same convention as the other Postgres suites.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from src.adapters.db.identity_store import PostgresAccountStore
from src.adapters.db.lead_store import PostgresLeadStore
from src.adapters.db.session import dispose_engine, session_factory
from src.domain.identity import AccountRole
from src.domain.lead import IntentTier, LeadEvent, LeadScore, LeadSignal, LeadState

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _requires_postgres(database_url_or_skip: str) -> None:
    """The marker above is documentation; *this* is what actually skips -- see the twin note
    in `test_adapters_cart_store_postgres.py`. Without it this module hangs the whole run
    when Postgres is unreachable instead of skipping."""


@pytest.fixture(autouse=True)
async def _cleanup_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()


def _store() -> PostgresLeadStore:
    return PostgresLeadStore(session_factory())


def scorer(events: tuple[LeadEvent, ...]) -> LeadScore:
    weight = min(1.0, 0.2 * len(events))
    signal = LeadSignal(
        name="added_to_cart",
        value=1.0,
        weight=weight,
        contribution=weight,
        explanation=f"{len(events)} action(s) on this car",
    )
    tier = IntentTier.HIGH if weight >= 0.6 else IntentTier.LOW
    return LeadScore(tier=tier, score=weight, signals=(signal,), explanation=tier.label)


async def _buyer() -> uuid.UUID:
    """`leads.buyer_account_id` is a foreign key, so these need a real account row."""
    accounts = PostgresAccountStore(session_factory())
    email = f"lead-{uuid.uuid4().hex[:12]}@example.com"
    await accounts.request_otp(email=email, role=AccountRole.BUYER, now=NOW)
    account, _token, _created = await accounts.verify_otp(
        email=email,
        role=AccountRole.BUYER,
        code="123456",
        full_name="Postgres Lead Buyer",
        phone="+49 170 1234567",
        profile_fields={"city": "Berlin", "country": "DE"},
        now=NOW,
    )
    return account.id


async def _seeded_listing() -> tuple[uuid.UUID, uuid.UUID, str, str]:
    """A real listing *with* a dealer -- `leads` has a foreign key to each. Uses whatever the
    seeded catalogue holds rather than inserting one; a test that seeded its own would be
    testing the seeder."""
    from sqlalchemy import select

    from src.adapters.db.models import ListingRow

    async with session_factory()() as session:
        row = (
            await session.scalars(
                select(ListingRow).where(ListingRow.dealer_id.isnot(None)).limit(1)
            )
        ).first()
    assert row is not None, "no listing with a dealer in the database -- run `make seed` first"
    return row.id, row.dealer_id, str(row.source), str(row.source_id)


async def record(
    store: PostgresLeadStore,
    buyer: uuid.UUID,
    listing: tuple[uuid.UUID, uuid.UUID, str, str],
    *,
    event: LeadEvent = LeadEvent.CART_ADD,
    summary: str = "Buying · suv · budget EUR 30,000",
    now: datetime = NOW,
):
    listing_id, dealer_id, source, source_id = listing
    return await store.record_event(
        buyer_account_id=buyer,
        dealer_id=dealer_id,
        listing_id=listing_id,
        source=source,
        source_id=source_id,
        requirement_summary=summary,
        event=event,
        score_with=scorer,
        now=now,
    )


# -- durability ----------------------------------------------------------------------


async def test_a_lead_survives_a_restart_with_its_breakdown_intact() -> None:
    buyer, listing = await _buyer(), await _seeded_listing()
    written, is_new = await record(_store(), buyer, listing)
    assert is_new

    reloaded = await _store().get(listing[1], written.id)

    assert reloaded is not None
    assert reloaded.score.tier is written.score.tier
    assert reloaded.score.score == written.score.score
    # The sentences, not just the numbers: the panel is the reasoning.
    assert [s.explanation for s in reloaded.score.signals] == [
        s.explanation for s in written.score.signals
    ]
    assert reloaded.requirement_summary == written.requirement_summary


async def test_for_dealer_returns_what_was_written() -> None:
    buyer, listing = await _buyer(), await _seeded_listing()
    await record(_store(), buyer, listing)

    leads = await _store().for_dealer(listing[1])

    assert any(lead.buyer_account_id == buyer for lead in leads)


# -- one lead per buyer per car (gate 15.1, against the real primary key) ------------


async def test_a_second_action_updates_the_same_row() -> None:
    buyer, listing = await _buyer(), await _seeded_listing()
    first, _ = await record(_store(), buyer, listing)
    second, is_new = await record(
        _store(), buyer, listing, event=LeadEvent.CHECKOUT_OPENED, now=NOW + timedelta(hours=1)
    )

    assert not is_new
    assert second.id == first.id
    assert set(second.events) == {LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED}

    mine = [
        lead for lead in await _store().for_dealer(listing[1]) if lead.buyer_account_id == buyer
    ]
    assert len(mine) == 1, "the second action created a second row"


async def test_the_reloaded_score_reflects_the_accumulated_events() -> None:
    buyer, listing = await _buyer(), await _seeded_listing()
    await record(_store(), buyer, listing)
    await record(_store(), buyer, listing, event=LeadEvent.CHECKOUT_OPENED)
    written, _ = await record(_store(), buyer, listing, event=LeadEvent.BOOKING_SUBMITTED)

    reloaded = await _store().get(listing[1], written.id)

    assert reloaded is not None
    assert reloaded.score.tier is IntentTier.HIGH
    assert "3 action(s)" in reloaded.score.signals[0].explanation


# -- dealer scoping, inside the SQL (gate 15.5) --------------------------------------


async def test_another_dealer_cannot_read_the_lead() -> None:
    buyer, listing = await _buyer(), await _seeded_listing()
    written, _ = await record(_store(), buyer, listing)

    stranger = uuid.uuid4()
    assert await _store().get(stranger, written.id) is None
    assert await _store().for_dealer(stranger) == ()


async def test_another_dealer_cannot_mark_it_contacted() -> None:
    buyer, listing = await _buyer(), await _seeded_listing()
    written, _ = await record(_store(), buyer, listing)

    assert await _store().set_state(uuid.uuid4(), written.id, LeadState.CONTACTED) is None

    reloaded = await _store().get(listing[1], written.id)
    assert reloaded is not None and reloaded.state is LeadState.NEW


async def test_marking_contacted_persists_across_a_restart() -> None:
    buyer, listing = await _buyer(), await _seeded_listing()
    written, _ = await record(_store(), buyer, listing)

    await _store().set_state(listing[1], written.id, LeadState.CONTACTED)

    reloaded = await _store().get(listing[1], written.id)
    assert reloaded is not None and reloaded.state is LeadState.CONTACTED
