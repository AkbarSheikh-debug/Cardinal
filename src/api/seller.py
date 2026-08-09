"""The seller console's transport -- PLAN-02 P15. Routes only.

**Every route resolves the dealer from the signed-in seller's own profile**, never from a
path or query parameter. There is no `dealer_id` anywhere in a signature here, which is what
makes gate 15.5 ("seller A never sees seller B's leads") a property of the route shape rather
than a filter someone has to remember -- the same discipline `src/api/cart.py` applies to
accounts, and it holds all the way down because `LeadStore`'s every method takes a dealer id
it can only get from here.

`GET /seller/events` reuses `QueueUISink` -- the transport `GET /sessions/{id}/events` already
streams A2UI messages over (PLAN-02 §0.4). A second consumer, no message broker, no polling
loop, and one fewer thing to configure in nginx that could silently buffer.

Every path is `/seller/<something>`; bare `/seller` is deliberately absent because it is the
*page*, and a proxy cannot tell a navigation from a fetch by path alone (D-076, the same
collision `/cart` hit).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.adapters.dealer_store import DealerDirectory
from src.adapters.identity_store import AccountStore
from src.adapters.lead_store import LeadStore
from src.api.auth import require_role
from src.api.leads import lead_payload
from src.domain.dealer import Dealer
from src.domain.identity import Account, AccountRole
from src.domain.lead import IntentTier, Lead, LeadState
from src.mcp.ui.sink import QueueUISink

router = APIRouter()

#: Newest first within a tier, highest tier first. A dealer opening this screen wants the
#: call they should make right now at the top, and recency breaks the tie because two High
#: leads are equally urgent but one of them is colder.
_TIER_ORDER = {IntentTier.HIGH: 0, IntentTier.MEDIUM: 1, IntentTier.LOW: 2}


class SellerEventHub:
    """One `QueueUISink` per dealer, created on first use.

    Per *dealer*, not per seller account: two salespeople signed in for the same dealership
    are looking at the same inbox, and giving them separate queues would mean a lead reaching
    whichever one happened to connect first. `publish` fans out to every open stream for that
    dealer instead.
    """

    def __init__(self) -> None:
        self._sinks: dict[uuid.UUID, list[QueueUISink]] = defaultdict(list)

    def subscribe(self, dealer_id: uuid.UUID) -> QueueUISink:
        sink = QueueUISink()
        self._sinks[dealer_id].append(sink)
        return sink

    def unsubscribe(self, dealer_id: uuid.UUID, sink: QueueUISink) -> None:
        streams = self._sinks.get(dealer_id)
        if streams and sink in streams:
            streams.remove(sink)

    def subscriber_count(self, dealer_id: uuid.UUID) -> int:
        return len(self._sinks.get(dealer_id, []))

    async def publish(self, dealer_id: uuid.UUID, message: dict[str, Any]) -> None:
        for sink in list(self._sinks.get(dealer_id, [])):
            await sink.push([message])


# -- dependencies -----------------------------------------------------------------------


def lead_store(request: Request) -> LeadStore:
    store: LeadStore = request.app.state.lead_store
    return store


def account_store(request: Request) -> AccountStore:
    store: AccountStore = request.app.state.account_store
    return store


def dealers(request: Request) -> DealerDirectory:
    directory: DealerDirectory = request.app.state.dealers
    return directory


def event_hub(request: Request) -> SellerEventHub:
    hub: SellerEventHub = request.app.state.seller_events
    return hub


async def _seller_dealer(request: Request) -> tuple[Account, uuid.UUID]:
    """The signed-in seller and the dealership they represent.

    A seller with no `dealer_id` gets a 409, not an empty list: "you have no leads" and "your
    account was never linked to a dealership" are different problems, and answering the second
    with the first is how somebody spends an afternoon wondering why the demo is broken.
    """
    account = await require_role(request, AccountRole.SELLER)
    profile = await account_store(request).get_seller_profile(account.id)
    if profile is None or profile.dealer_id is None:
        # Deliberately does *not* say "sign in again": the profile is written once, at
        # signup, so `verify_otp` reuses the existing account and ignores whatever the form
        # sends on a later login. Telling someone to retry the one action that cannot work is
        # worse than telling them nothing. The signup form now marks the dealership
        # `required`, so new accounts cannot reach this state -- only ones created before
        # that can, and for those a fresh address is genuinely the fix under demo auth.
        raise HTTPException(
            status_code=409,
            detail="this seller account is not linked to a dealership. The dealership is set "
            "once, when the account is created, so signing in again will not change it -- "
            "sign up with a different email and choose a dealership on the form.",
        )
    return account, profile.dealer_id


def _sort_key(lead: Lead) -> tuple[int, float]:
    return (_TIER_ORDER[lead.score.tier], -lead.created_at.timestamp())


# -- routes -----------------------------------------------------------------------------


@router.get("/seller/dealers")
async def list_dealers(request: Request) -> list[dict[str, Any]]:
    """The dealership picker on the login form.

    Unauthenticated on purpose: it is the *signup* form that needs it, and everything it
    returns is already public on every result card a buyer sees (name, city, rating,
    verification). Nothing account-shaped is in here.
    """
    directory = await dealers(request).all()
    return [_dealer_option(d) for d in directory]


def _dealer_option(dealer: Dealer) -> dict[str, Any]:
    return {
        "id": str(dealer.id),
        "display_name": dealer.display_name,
        "city": dealer.city,
        "country": dealer.country,
        "verified": dealer.is_verified,
    }


@router.get("/seller/leads")
async def list_leads(request: Request) -> dict[str, Any]:
    """Every lead for this seller's dealership, urgent first, plus the analytics strip."""
    account, dealer_id = await _seller_dealer(request)
    now = datetime.now(UTC)
    leads = sorted(await lead_store(request).for_dealer(dealer_id), key=_sort_key)

    accounts = account_store(request)
    store = request.app.state.store
    payloads: list[dict[str, Any]] = []
    for lead in leads:
        buyer = await accounts.get_account(lead.buyer_account_id)
        listing = await store.fetch(lead.source, lead.source_id)
        payloads.append(lead_payload(lead, account=buyer, now=now, listing=listing))

    dealer = await dealers(request).get(dealer_id)
    return {
        "dealer": _dealer_option(dealer) if dealer is not None else None,
        "seller": {"full_name": account.full_name, "email": account.email},
        "leads": payloads,
        "analytics": _analytics(leads, now=now),
    }


def _analytics(leads: list[Lead], *, now: datetime) -> dict[str, Any]:
    """Lead volume by tier over time -- PLAN-02 §P15's `[MVP]` analytics line.

    Deliberately small: counts by tier, and counts by tier per day for the last week. A
    dealer's actual question is "is this getting better or worse", and a stacked column per
    day answers it without this becoming a BI tool nobody asked for.
    """
    by_tier = {tier.value: 0 for tier in IntentTier}
    for lead in leads:
        by_tier[lead.score.tier.value] += 1

    days: list[dict[str, Any]] = []
    for offset in range(6, -1, -1):
        day = (now - timedelta(days=offset)).date()
        counts = {tier.value: 0 for tier in IntentTier}
        for lead in leads:
            if lead.created_at.date() == day:
                counts[lead.score.tier.value] += 1
        days.append({"date": day.isoformat(), **counts})

    return {
        "total": len(leads),
        "by_tier": by_tier,
        "open": sum(1 for lead in leads if lead.state in (LeadState.NEW, LeadState.VIEWED)),
        "overdue": sum(1 for lead in leads if lead.is_overdue(now)),
        "by_day": days,
    }


@router.post("/seller/leads/{lead_id}/contacted")
async def mark_contacted(request: Request, lead_id: str) -> dict[str, Any]:
    _account, dealer_id = await _seller_dealer(request)
    try:
        parsed = uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="lead_id must be a uuid") from None

    lead = await lead_store(request).set_state(dealer_id, parsed, LeadState.CONTACTED)
    if lead is None:
        # The store already scoped the lookup to this dealer, so a miss means "not yours or
        # not there". One answer for both, for the same reason `/cart/checkout` has one.
        raise HTTPException(status_code=404, detail="no such lead")
    buyer = await account_store(request).get_account(lead.buyer_account_id)
    listing = await request.app.state.store.fetch(lead.source, lead.source_id)
    return lead_payload(lead, account=buyer, now=datetime.now(UTC), listing=listing)


@router.get("/seller/events")
async def seller_events(request: Request) -> StreamingResponse:
    """Live lead notifications for this dealership (PLAN-02 §0.4).

    The payload is deliberately a *nudge*, not a lead: `{kind: "lead", new: bool, lead_id}`.
    The console refetches `/seller/leads` when one arrives, which means the SSE channel never
    becomes a second place buyer contact details are serialised, and there is one code path
    that decides what a seller may see instead of two that have to agree.
    """
    _account, dealer_id = await _seller_dealer(request)
    hub = event_hub(request)
    sink = hub.subscribe(dealer_id)

    async def stream() -> AsyncIterator[str]:
        try:
            # An immediate frame so a client knows the stream is live rather than pending --
            # and so a test can assert the subscription exists before the event it waits for.
            yield f"data: {json.dumps({'kind': 'ready'})}\n\n"
            async for message in sink.stream():
                yield f"data: {json.dumps(message)}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            hub.unsubscribe(dealer_id, sink)

    return StreamingResponse(stream(), media_type="text/event-stream")
