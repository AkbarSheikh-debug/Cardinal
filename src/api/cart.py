"""Cart transport -- PLAN-02 P14. Routes only.

**Every route scopes to the signed-in account, resolved from the bearer token.** There is no
`account_id` path parameter and no way to supply one in a body: the account is whoever the
cookie says it is, which is what makes gate 14.11's cross-account isolation a property of the
route shape rather than a check somebody has to remember. `CartStore` is keyed the same way,
so the guarantee holds all the way down to the SQL.

The cart deliberately carries **no payment surface of its own**. `POST /cart/checkout` opens
the *booking form* MCP App -- the same `ui://booking/form` P7 built, prefilled from the cart
line -- and then gets out of the way. Everything after that is P7/P8's existing, already-gated
sequence:

    open_booking_form -> [human fills and submits] -> submit_booking_draft
      -> open_checkout -> [human clicks Pay] -> mint_gesture_token -> confirm_booking

This module never calls `submit_booking_draft`, never mints a gesture token, and never
touches `confirm_booking`. It is one more caller of the front of that chain, not a second
path to the end of it (CONSTITUTION I.2, PLAN-02 §0.1) -- which is what gate 14.6's static
scan asserts.

Opening the *form* rather than jumping straight to checkout is deliberate: the form-fill App
is itself a mandatory MCP App, and skipping it would mean a cart purchase never collected the
details a booking needs.

**Every route here lives under `/cart/`, with a trailing segment -- there is deliberately no
bare `GET /cart`.** `/cart` is also the *page* the buyer navigates to, and a proxy cannot tell
a navigation to `/cart` from a `fetch("/cart")` by path alone. PLAN-02 §2.2 flags the general
trap; this is the specific collision it did not foresee. Keeping the API strictly one level
down means `location /cart/` (nginx) and `"/cart/"` (Vite) proxy the API while bare `/cart`
falls through to the SPA, by path shape rather than by content negotiation. See D-076.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.adapters.cart_store import CartStore, new_cart_item
from src.adapters.dealer_store import DealerDirectory
from src.adapters.store import ListingStore
from src.api.auth import current_account, require_role
from src.api.leads import record_lead
from src.domain.cart import Cart, CartItem
from src.domain.dealer import PayeeIdentity
from src.domain.enums import OfferType
from src.domain.identity import AccountRole
from src.domain.lead import LeadEvent
from src.domain.listing import Listing, ListingSummary
from src.mcp.booking.resources import BOOKING_FORM_URI

router = APIRouter()


def cart_store(request: Request) -> CartStore:
    store: CartStore = request.app.state.cart_store
    return store


def listing_store(request: Request) -> ListingStore:
    store: ListingStore = request.app.state.store
    return store


def dealers(request: Request) -> DealerDirectory:
    directory: DealerDirectory = request.app.state.dealers
    return directory


def _offer_type_from(value: Any) -> OfferType:
    try:
        return OfferType(str(value).strip().lower())
    except ValueError:
        raise HTTPException(
            status_code=422, detail="offer_type must be 'buy', 'rent' or 'both'"
        ) from None


async def _payload(request: Request, cart: Cart) -> dict[str, Any]:
    """The cart, enriched with what each line needs to be shown and paid for.

    Enrichment happens here rather than being stored on `CartItem`: a price or a dealer's
    verification status captured at add-to-cart time goes stale the moment either changes,
    and a checkout that quotes a stale price is the worst possible way to find that out.
    """
    store = listing_store(request)
    directory = dealers(request)

    lines: list[dict[str, Any]] = []
    for item in cart.items:
        listing = await store.fetch(item.source, item.source_id)
        payee: PayeeIdentity | None = None
        if listing is not None:
            payee = await directory.payee(listing.dealer_id)
        lines.append(_line(item, listing, payee))

    return {
        "count": cart.count,
        "items": lines,
        # Deliberately no cart-wide total: `[MVP]` checkout runs on one line (PLAN-02 P14),
        # and a sum across a rental and a purchase is a number with no meaning.
        "checkout_is_single_item": True,
    }


def _line(item: CartItem, listing: Listing | None, payee: PayeeIdentity | None) -> dict[str, Any]:
    available = listing is not None and listing.is_available
    price = None
    if listing is not None:
        money = listing.price_buy if item.offer_type.is_buyable else None
        if money is None and listing.rental_rates is not None:
            money = listing.rental_rates.daily
        price = {"amount": str(money.amount), "currency": money.currency.value} if money else None
    return {
        "item_id": str(item.id),
        "source": item.source,
        "source_id": item.source_id,
        "offer_type": item.offer_type.value,
        "added_at": item.added_at.isoformat(),
        "available": available,
        "headline": _headline(listing),
        "condition": listing.condition.value if listing is not None else None,
        "price": price,
        # The payee block P14 renders before the pay button. `None` when the listing has no
        # dealer yet -- the UI shows that as "payee unknown", never as silence.
        "payee": _payee_payload(payee),
    }


def _headline(listing: Listing | None) -> str | None:
    return ListingSummary.from_listing(listing).headline if listing is not None else None


def _payee_payload(payee: PayeeIdentity | None) -> dict[str, Any] | None:
    if payee is None:
        return None
    return {
        "legal_name": payee.legal_name,
        "display_name": payee.display_name,
        "address": payee.address,
        "city": payee.city,
        "country": payee.country,
        "phone": payee.phone,
        "verification_status": payee.verification_status.value,
        "needs_flag": payee.needs_flag,
        "one_line": payee.one_line,
    }


@router.get("/cart/items")
async def read_cart(request: Request) -> dict[str, Any]:
    account = await require_role(request, AccountRole.BUYER)
    return await _payload(request, await cart_store(request).get(account.id))


@router.post("/cart/items")
async def add_item(request: Request) -> dict[str, Any]:
    """Adds a listing to the signed-in buyer's cart. Idempotent on the natural key."""
    account = await require_role(request, AccountRole.BUYER)
    body = await request.json()
    source = str(body.get("source", "")).strip()
    source_id = str(body.get("source_id", "")).strip()
    if not source or not source_id:
        raise HTTPException(status_code=422, detail="source and source_id are required")
    offer_type = _offer_type_from(body.get("offer_type", "buy"))

    listing = await listing_store(request).fetch(source, source_id)
    if listing is None:
        raise HTTPException(status_code=404, detail=f"no listing {source}:{source_id}")
    if not listing.is_available:
        raise HTTPException(status_code=409, detail="that listing has been withdrawn")
    # Refuse an intent the listing cannot honour, at the door: a rental added as a purchase
    # would only fail at checkout, after the buyer has committed attention to it.
    if offer_type.is_buyable and not listing.offer_type.is_buyable:
        raise HTTPException(status_code=409, detail="that listing is not for sale")
    if offer_type.is_rentable and not listing.offer_type.is_rentable:
        raise HTTPException(status_code=409, detail="that listing is not available to rent")

    cart = await cart_store(request).add(account.id, new_cart_item(listing, offer_type))
    # PLAN-02 P15: a cart-add is a qualifying intent action, so the dealer who owns this car
    # learns about it. `session_id` is optional and only supplies the *interview* (target
    # date, budget) to the scorer -- a buyer who added a car without ever talking to the
    # agent still produces a lead, just a quieter one. Never raises (`src/api/leads.py`).
    await record_lead(
        request,
        buyer_account_id=account.id,
        listing=listing,
        event=LeadEvent.CART_ADD,
        session_id=str(body.get("session_id") or "") or None,
    )
    return await _payload(request, cart)


@router.delete("/cart/items/{item_id}")
async def remove_item(request: Request, item_id: str) -> dict[str, Any]:
    account = await require_role(request, AccountRole.BUYER)
    try:
        parsed = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="item_id must be a uuid") from None
    cart = await cart_store(request).remove(account.id, parsed)
    return await _payload(request, cart)


@router.post("/cart/checkout")
async def start_checkout(request: Request) -> dict[str, Any]:
    """Open the booking form for one cart line, in the caller's own session.

    Takes `session_id` because the MCP App mounts over that session's SSE stream -- the same
    stream the chat rail on `/cart` is already listening to, which is what lets the App appear
    beside a live conversation rather than replacing it.
    """
    account = await require_role(request, AccountRole.BUYER)
    body = await request.json()
    session_id = str(body.get("session_id", "")).strip()
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id is required")
    try:
        item_id = uuid.UUID(str(body.get("item_id", "")))
    except ValueError:
        raise HTTPException(status_code=422, detail="item_id must be a uuid") from None

    cart = await cart_store(request).get(account.id)
    item = cart.find(item_id)
    if item is None:
        # The cart is already account-scoped, so a miss here means "not yours or not there".
        # One answer for both, for the same reason `/auth/verify-otp` has one.
        raise HTTPException(status_code=404, detail="no such item in your cart")

    listing = await listing_store(request).fetch(item.source, item.source_id)
    if listing is None or not listing.is_available:
        raise HTTPException(status_code=409, detail="that listing is no longer available")

    await request.app.state.orchestrator.ui_sink(session_id).push(
        [
            {
                "kind": "mcp_app_open",
                "resourceUri": BOOKING_FORM_URI,
                "toolName": "open_booking_form",
                "toolInput": {
                    "source": item.source,
                    "source_id": item.source_id,
                    "offer_type": item.offer_type.value,
                    "name": account.full_name,
                    "email": account.email,
                    "phone": account.phone,
                },
            }
        ]
    )
    # Remember that *this* session's next `submit_booking_draft` came from the cart, so the
    # hand-off in `src/api/main.py` knows to open checkout after it. Without this the form
    # would submit and nothing further would happen outside DEMO_MODE.
    request.app.state.cart_checkout_sessions.add(session_id)
    # PLAN-02 P15: the strongest intent signal short of confirming. Recorded here rather than
    # when the checkout *App* mounts, because this is the human click that caused it -- the
    # mount is a consequence, and hanging a lead off a consequence means a retry or a reload
    # of the same intent looks like a second one.
    await record_lead(
        request,
        buyer_account_id=account.id,
        listing=listing,
        event=LeadEvent.CHECKOUT_OPENED,
        session_id=session_id,
    )
    return {"opened": True, "resource_uri": BOOKING_FORM_URI, "item_id": str(item_id)}


@router.get("/cart/count")
async def cart_count(request: Request) -> dict[str, Any]:
    """What the header badge polls. Cheap, and 401s rather than 403s for a seller so the
    buyer header can treat "no cart" and "not signed in" identically."""
    account = await current_account(request)
    if account.role is not AccountRole.BUYER:
        return {"count": 0}
    return {"count": (await cart_store(request).get(account.id)).count}
