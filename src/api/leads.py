"""The one place a buyer action becomes a lead -- PLAN-02 P15.

`src/api/cart.py` and `src/api/main.py` both call `record_lead` and neither knows anything
about scoring, dealers or SSE. That matters more than tidiness: lead creation has to be
*impossible to do slightly differently* from three call sites, or the tier a dealer sees
starts depending on which button the buyer happened to press first.

Two properties this module is responsible for:

- **Never breaks the buyer's flow.** Every failure here is swallowed and logged. A dealer not
  learning about a lead is bad; a buyer's add-to-cart returning 500 because the dealer
  directory hiccuped is worse, and the buyer is the one who came here to do something.
- **Never leaks income.** It reads `RequirementProfile` (which has no income field) and the
  buyer's `Account` (name, email, phone -- released only because an intent action already
  happened, PLAN-02 §P15's privacy rule). `BuyerProfile` is read for exactly one thing,
  `customer_type`, and nothing else off it is ever passed on.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import Request

from src.adapters.lead_store import LeadStore
from src.domain.identity import CustomerType
from src.domain.lead import Lead, LeadEvent, LeadScore
from src.domain.lead_scoring import score_lead
from src.domain.listing import Listing, ListingSummary
from src.domain.profile import RequirementProfile

logger = logging.getLogger(__name__)


def requirement_summary(profile: RequirementProfile | None) -> str:
    """One line a salesperson can read in the two seconds before they pick up the phone.

    Built from filled slots only -- an unfilled slot is omitted rather than rendered as
    "budget: None", which reads like a system fault rather than like a buyer who hasn't said
    yet. Deliberately carries the *stated* budget: it is the single most useful thing on a
    lead, the buyer volunteered it, and it is not income.
    """
    if profile is None:
        return "No interview on record yet."
    parts: list[str] = []
    if profile.goal.is_filled and profile.goal.value is not None:
        parts.append("Renting" if profile.goal.value.is_rentable else "Buying")
    if profile.category.is_filled and profile.category.value:
        parts.append("/".join(c.value.replace("_", " ") for c in profile.category.value))
    if profile.budget.is_filled and profile.budget.value is not None:
        money = profile.budget.value
        parts.append(f"budget {money.currency.value} {money.amount:,.0f}")
    if profile.target_date.is_filled and profile.target_date.value is not None:
        parts.append(f"needed by {profile.target_date.value.isoformat()}")
    if profile.use_case.is_filled and profile.use_case.value:
        parts.append(str(profile.use_case.value))
    return " · ".join(parts) if parts else "Interview still in progress."


def _price_of(listing: Listing) -> Decimal | None:
    if listing.price_buy is not None:
        return listing.price_buy.amount
    if listing.rental_rates is not None:
        return listing.rental_rates.monthly.amount
    return None


async def record_lead(
    request: Request,
    *,
    buyer_account_id: uuid.UUID,
    listing: Listing,
    event: LeadEvent,
    session_id: str | None = None,
    now: datetime | None = None,
) -> Lead | None:
    """Records one qualifying action. Returns the lead, or `None` when there is nothing to
    route it to (a listing with no dealer, or leads not wired up in this process).

    Never raises. See this module's docstring.
    """
    try:
        return await _record(
            request,
            buyer_account_id=buyer_account_id,
            listing=listing,
            event=event,
            session_id=session_id,
            now=now,
        )
    except Exception:  # deliberately broad -- see this module's docstring
        logger.exception("lead recording failed for %s:%s", listing.source, listing.source_id)
        return None


async def _record(
    request: Request,
    *,
    buyer_account_id: uuid.UUID,
    listing: Listing,
    event: LeadEvent,
    session_id: str | None,
    now: datetime | None,
) -> Lead | None:
    store: LeadStore | None = getattr(request.app.state, "lead_store", None)
    if store is None or listing.dealer_id is None:
        # A listing whose `dealer_id` predates the P13 re-seed has nobody to route to. That
        # is a data gap, not an error the buyer should see -- gate 13.1 asserts a freshly
        # generated catalogue has none.
        return None

    moment = now or datetime.now(UTC)
    profile = _profile_for(request, session_id)
    is_corporate = await _is_corporate(request, buyer_account_id)
    budget = (
        profile.budget.value.amount
        if profile is not None and profile.budget.is_filled and profile.budget.value is not None
        else None
    )
    target: date | None = (
        profile.target_date.value if profile is not None and profile.target_date.is_filled else None
    )
    price = _price_of(listing)

    def score_with(events: tuple[LeadEvent, ...]) -> LeadScore:
        return score_lead(
            events=events,
            target_date=target,
            today=moment.date(),
            budget=budget,
            price=price,
            return_sessions=1,
            is_corporate=is_corporate,
        )

    lead, is_new = await store.record_event(
        buyer_account_id=buyer_account_id,
        dealer_id=listing.dealer_id,
        listing_id=listing.id,
        source=listing.source,
        source_id=listing.source_id,
        requirement_summary=requirement_summary(profile),
        event=event,
        score_with=score_with,
        now=moment,
    )

    hub = getattr(request.app.state, "seller_events", None)
    if hub is not None:
        await hub.publish(lead.dealer_id, {"kind": "lead", "new": is_new, "lead_id": str(lead.id)})
    return lead


def _profile_for(request: Request, session_id: str | None) -> RequirementProfile | None:
    """The buyer's interview, if this action carried a session id.

    `None` is an ordinary outcome, not a failure: a buyer can add a car to their cart without
    the agent having interviewed them, and `score_lead` treats a missing target date and a
    missing budget as "not stated" rather than as zero.
    """
    if not session_id:
        return None
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return None
    state = orchestrator.state(session_id)
    return state.profile if state is not None else None


async def _is_corporate(request: Request, account_id: uuid.UUID) -> bool:
    """The *only* thing read off `BuyerProfile`. `annual_income`/`income_band`/`employer` are
    never touched here and never travel onward (PLAN-02 §0.3, gates 15.7 / 12.7)."""
    store = getattr(request.app.state, "account_store", None)
    if store is None:
        return False
    profile = await store.get_buyer_profile(account_id)
    return profile is not None and profile.customer_type is CustomerType.CORPORATE


def _listing_payload(listing: Listing | None) -> dict[str, Any] | None:
    """What the car is, in the words a dealer uses about it. Deliberately a small projection
    rather than the whole `Listing`: this is a seller-facing payload, and a route that dumps
    an entity starts carrying fields nobody reviewed for the context (D-026's reasoning)."""
    if listing is None:
        return None
    price = listing.price_buy or (listing.rental_rates.monthly if listing.rental_rates else None)
    return {
        "headline": ListingSummary.from_listing(listing).headline,
        "price": {"amount": str(price.amount), "currency": price.currency.value} if price else None,
        "condition": listing.condition.value,
        "available": listing.is_available,
    }


def lead_payload(
    lead: Lead,
    *,
    account: Any,
    now: datetime,
    listing: Listing | None = None,
) -> dict[str, Any]:
    """The seller-facing projection of a lead.

    Built field by field rather than `model_dump()`-ing a `Lead` plus an `Account`, for the
    reason D-026 gives for `ScoreBreakdown`'s dedicated render model: a payload that dumps a
    whole entity starts carrying fields nobody reviewed for this context, and *this* context
    is the one where that mistake means a dealer sees a stranger's salary band.

    Contact details are here because a lead exists, and a lead only exists after an intent
    action on this dealer's car (PLAN-02 §P15's privacy rule, `Lead`'s own docstring).
    """
    deadline = lead.sla_deadline
    return {
        "id": str(lead.id),
        "state": lead.state.value,
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
        "source": lead.source,
        "source_id": lead.source_id,
        # Resolved fresh on read rather than frozen onto the lead: a salesperson picking up
        # the phone needs the car's *current* price, and "mock_autobazaar:AB-1001" is not a
        # thing anyone can talk to a buyer about. `None` when the listing has since been
        # withdrawn -- which the console shows as exactly that, rather than as silence.
        "listing": _listing_payload(listing),
        "requirement_summary": lead.requirement_summary,
        "events": [e.value for e in lead.events],
        "buyer": {
            "full_name": getattr(account, "full_name", None),
            "email": getattr(account, "email", None),
            "phone": getattr(account, "phone", None),
        },
        "tier": lead.score.tier.value,
        # The phrasing gate 15.8 asserts on rendered text. Sent from here rather than
        # assembled in the client so there is exactly one place the wording lives.
        "tier_label": lead.score.tier.label,
        "guidance": lead.score.tier.guidance,
        "score": lead.score.score,
        "explanation": lead.score.explanation,
        "signals": [
            {
                "name": s.name,
                "value": s.value,
                "weight": s.weight,
                "contribution": s.contribution,
                "explanation": s.explanation,
            }
            for s in lead.score.ranked_signals
        ],
        "sla_deadline": deadline.isoformat() if deadline is not None else None,
        "overdue": lead.is_overdue(now),
    }
