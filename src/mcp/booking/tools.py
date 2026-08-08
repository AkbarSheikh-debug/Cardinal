"""The five `booking-mcp` tools. `open_booking_form`/`submit_booking_draft` got real bodies in
PHASE-7; `open_checkout`, `mint_gesture_token` and `confirm_booking` get theirs here
(PHASE-8 §3-§7).

`open_booking_form` and `open_checkout` are model-and-app visible -- the model opens the
surface, a human acts inside it. `submit_booking_draft`, `mint_gesture_token` and
`confirm_booking` are app-only: all three fire from a view's own handler, never from the
model's initiative, and `confirm_booking` additionally never reaches the model's tool list at
all (CONSTITUTION I.2, gate 8.2).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from claude_agent_sdk import tool

from src.adapters.booking_store import BookingStore, InMemoryBookingStore, session_ref_to_uuid
from src.adapters.payments.mock import MockPaymentGateway
from src.adapters.payments.protocol import PaymentGateway
from src.adapters.protocol import ListingNotFoundError, QuoteNotAvailableError
from src.adapters.registry import adapter_by_name
from src.adapters.store import InMemoryListingStore, ListingStore
from src.domain.booking import Booking, BookingEvent, BookingState, Customer, new_audit_entry
from src.domain.dates import DateRange
from src.domain.enums import OfferType
from src.domain.financing import (
    MAX_DOWN_PAYMENT_PCT,
    MAX_TERM_MONTHS,
    MIN_TERM_MONTHS,
    FinancingTerms,
    compute_monthly_payment,
)
from src.domain.marketplace import Quote, QuoteTerms
from src.domain.money import Money
from src.domain.payments import OUTCOME_MESSAGES, PaymentIntent, PaymentOutcome
from src.mcp.audience import APP_ONLY, MODEL_AND_APP, ToolSpec
from src.mcp.booking.gesture import GESTURE_TOKEN_TTL_SECONDS, GestureTokenStore
from src.mcp.booking.resources import BOOKING_FORM_URI, CHECKOUT_URI
from src.mcp.schema import enum_property, strict_schema
from src.mcp.ui.sink import NullUISink, UISink

#: In-memory booking-draft store, `[MVP]` (mirrors P4's working-state-first posture, D-019):
#: keyed by the view-generated `booking_draft_id` so a retried submit stays idempotent. `[SCALE]`
#: is Postgres, the same way P4's decision journal graduated from in-memory once P0 gave it a
#: table -- nothing about this shape changes when that lands, only where it's kept.
_booking_drafts: dict[str, dict[str, Any]] = {}

#: `open_checkout`, `mint_gesture_token`, `submit_booking_draft` and `confirm_booking` for one
#: session are four *separate* HTTP requests (`POST /mcp-apps/{session}/rpc`), each of which
#: builds a fresh `McpSdkServerConfig` (`src/mcp/booking/server.py`'s `build_booking_server`
#: takes no server-lifetime cache of its own). A gesture token minted in one request has to
#: still be there when the next request tries to spend it, and an idempotency replay has to
#: see what an earlier request inserted -- so these three live at module scope, the same
#: process-lifetime sharing `_booking_drafts` above already relies on, not inside
#: `build_tool_specs`'s closure where a fresh instance would appear on every call and silently
#: forget everything the request before it just did.
_default_gesture_tokens = GestureTokenStore()
_default_booking_store: BookingStore = InMemoryBookingStore()
_default_payment_gateway: PaymentGateway = MockPaymentGateway()
#: `generate_catalogue()`'s default seed is fixed (`DEFAULT_SEED`, gate 1.6) so every call
#: produces a byte-identical 240-row catalogue -- sharing one instance is purely to avoid
#: regenerating it on every request a caller doesn't supply its own `ListingStore` for.
_default_listing_store: ListingStore = InMemoryListingStore.seeded()


def booking_draft(draft_id: str) -> dict[str, Any] | None:
    """Read-only lookup, used by `open_checkout`/`confirm_booking` to recover the listing
    reference and customer details a submitted draft carries."""
    return _booking_drafts.get(draft_id)


class _CheckoutInputError(RuntimeError):
    """A draft is missing what checkout needs to price it -- a caller bug (the form was never
    opened with a listing reference) rather than something the payment gateway could ever see.
    """


def _text_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def _error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


async def _price_draft(store: ListingStore, form_fields: dict[str, Any]) -> tuple[uuid.UUID, Quote]:
    """Resolves a draft's listing and prices it fresh -- `open_checkout` and `confirm_booking`
    both call this rather than trusting any total a client might supply, per PHASE-8 §7: "the
    displayed figure is never trusted." Reuses P1's own `adapter.quote` (the same pricing path
    `get_quote` uses) instead of a second, checkout-specific pricing formula.
    """
    source = form_fields.get("source")
    source_id = form_fields.get("source_id")
    offer_type = form_fields.get("offer_type")
    if not source or not source_id or not offer_type:
        raise _CheckoutInputError(
            "this booking draft has no source/source_id/offer_type -- "
            "was the booking form opened via open_booking_form?"
        )
    adapter = adapter_by_name(store, source)
    listing = await store.fetch(source, source_id)
    if listing is None:
        raise ListingNotFoundError(f"no listing {source_id!r} on {source!r}")

    terms_kwargs: dict[str, Any] = {}
    if offer_type == OfferType.RENT.value:
        start, end = form_fields.get("window_start"), form_fields.get("window_end")
        if start and end:
            terms_kwargs["window"] = DateRange(start=start, end=end)
    quote = await adapter.quote(source_id, QuoteTerms(**terms_kwargs))
    return listing.id, quote


def _server_monthly_payment(total: Money, financing_args: dict[str, Any] | None) -> str | None:
    if financing_args is None:
        return None
    terms = FinancingTerms(
        term_months=financing_args["term_months"],
        down_payment_pct=Decimal(str(financing_args["down_payment_pct"])),
        apr_pct=Decimal(str(financing_args["apr_pct"])),
    )
    return str(compute_monthly_payment(total, terms).amount)


def _booking_response(booking: Booking, *, server_monthly_payment: str | None) -> dict[str, Any]:
    """The one place a `Booking` becomes `confirm_booking`'s wire response -- built entirely
    from the stored booking, never from anything computed only on the first attempt, so a
    replayed idempotent call (gate 8.5) reconstructs an identical payload from the identical
    row rather than needing a separate response cache.
    """
    last = booking.audit[-1] if booking.audit else None
    outcome_code = last.note if last is not None else booking.state.value
    try:
        message = OUTCOME_MESSAGES[PaymentOutcome(outcome_code)]
    except ValueError:
        message = ""
    payload: dict[str, Any] = {
        "booking_id": str(booking.id),
        "state": booking.state.value,
        "outcome": outcome_code,
        "message": message,
    }
    if server_monthly_payment is not None:
        payload["server_monthly_payment_eur"] = server_monthly_payment
    return payload


def _payment_method_schema() -> dict[str, Any]:
    """CONSTITUTION IV.2: `last4` and a client-derived outcome label are the *only*
    card-shaped things this schema accepts -- there is no field here a full card number could
    even be put in. See DECISIONS.md D-036.
    """
    return {
        "type": "object",
        "properties": {
            "last4": {
                "type": "string",
                "description": "Last four digits only -- the App never sends the full number.",
            },
            "simulated_outcome": enum_property(
                tuple(o.value for o in PaymentOutcome),
                description="What the App's own client-side test-card table determined "
                "(PHASE-8 §5). A real integration would read this from the gateway's own "
                "response, not the client -- this field only exists because the gateway is "
                "mocked and the card number that would normally decide it never leaves the App.",
            ),
        },
        "required": ["last4", "simulated_outcome"],
        "additionalProperties": False,
    }


def _financing_schema() -> dict[str, Any]:
    return {
        "type": ["object", "null"],
        "description": "Chosen financing terms for a purchase, or null for a rental or a "
        "cash purchase. Recomputed server-side against the authoritative price -- PHASE-8 §7.",
        "properties": {
            "term_months": {
                "type": "integer",
                "minimum": MIN_TERM_MONTHS,
                "maximum": MAX_TERM_MONTHS,
            },
            "down_payment_pct": {
                "type": "number",
                "minimum": 0,
                "maximum": float(MAX_DOWN_PAYMENT_PCT),
            },
            "apr_pct": {"type": "number", "minimum": 0, "maximum": 100},
        },
        "required": ["term_months", "down_payment_pct", "apr_pct"],
        "additionalProperties": False,
    }


def build_tool_specs(
    *,
    session_id: str = "unbound",
    sink: UISink | None = None,
    store: ListingStore | None = None,
    booking_store: BookingStore | None = None,
    payment_gateway: PaymentGateway | None = None,
) -> list[ToolSpec]:
    active_sink: UISink = sink if sink is not None else NullUISink()
    #: Falls back to the shared module-level defaults above, not a fresh instance -- see the
    #: comment on `_default_booking_store` for why a per-call instance would silently break
    #: the gesture-token/idempotency flow across separate requests.
    active_store: ListingStore = store if store is not None else _default_listing_store
    active_bookings: BookingStore = (
        booking_store if booking_store is not None else _default_booking_store
    )
    active_gateway: PaymentGateway = (
        payment_gateway if payment_gateway is not None else _default_payment_gateway
    )
    gesture_tokens = _default_gesture_tokens

    @tool(
        "open_booking_form",
        "Open the booking form for one listing as an MCP App, pre-filled with the offer "
        "type and any dates already known from the conversation. Call this when the user "
        "has settled on a specific listing and an offer type (buy or rent) and is ready to "
        "move from browsing to booking -- not before a listing is at least tentatively "
        "chosen. This only opens the form for a human to review and complete; it never "
        "submits or confirms anything by itself.",
        strict_schema(
            {
                "source": {"type": "string"},
                "source_id": {"type": "string"},
                "offer_type": enum_property(
                    tuple(o.value for o in OfferType if o is not OfferType.BOTH),
                    description="Which path this booking is for.",
                ),
                "window_start": {"type": "string", "description": "ISO date. Rental only."},
                "window_end": {"type": "string", "description": "ISO date. Rental only."},
            },
            required=["source", "source_id", "offer_type"],
        ),
    )
    async def open_booking_form(args: dict[str, Any]) -> dict[str, Any]:
        # The model never sees a wire payload (PHASE-6's same rule for render_* tools) -- it
        # gets a short confirmation that the App opened, while the browser learns to actually
        # mount it from this "mount an MCP App" message pushed through the session's own
        # SSE transport (reusing P6's UISink/QueueUISink rather than inventing a second
        # channel, per PROGRESS.md's note when P6 landed).
        await active_sink.push(
            [
                {
                    "kind": "mcp_app_open",
                    "resourceUri": BOOKING_FORM_URI,
                    "toolName": "open_booking_form",
                    "toolInput": args,
                }
            ]
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Opened the booking form for {args.get('source_id')} "
                        f"({args.get('offer_type')}) -- waiting on the user to review "
                        "and submit it."
                    ),
                }
            ]
        }

    @tool(
        "open_checkout",
        "Open the checkout MCP App for a booking draft that has already been submitted, so "
        "the user can review the priced total, optionally choose financing terms, and enter "
        "payment details inside the conversation. Call this when a booking draft id exists "
        "and the user is ready to pay, typically right after submit_booking_draft has "
        "produced that draft. This renders the payment surface only, priced fresh from the "
        "listing -- it never charges a card or confirms a booking.",
        strict_schema({"booking_draft_id": {"type": "string"}}),
    )
    async def open_checkout(args: dict[str, Any]) -> dict[str, Any]:
        draft_id = args["booking_draft_id"]
        draft = booking_draft(draft_id)
        if draft is None:
            return _error_result(f"no booking draft {draft_id!r} -- submit the booking form first")
        form_fields = draft.get("form_fields", {})
        try:
            _, quote = await _price_draft(active_store, form_fields)
        except (_CheckoutInputError, KeyError, ListingNotFoundError, QuoteNotAvailableError) as exc:
            return _error_result(str(exc))

        tool_input = {
            "booking_draft_id": draft_id,
            "source": form_fields.get("source"),
            "source_id": form_fields.get("source_id"),
            "offer_type": form_fields.get("offer_type"),
            "total_amount": str(quote.total.amount),
            "total_currency": quote.total.currency.value,
            "customer_name": form_fields.get("name"),
            "window_start": form_fields.get("window_start"),
            "window_end": form_fields.get("window_end"),
        }
        await active_sink.push(
            [
                {
                    "kind": "mcp_app_open",
                    "resourceUri": CHECKOUT_URI,
                    "toolName": "open_checkout",
                    "toolInput": tool_input,
                }
            ]
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Opened checkout for {form_fields.get('source_id')} -- total "
                        f"{quote.total} -- waiting on the user to pay."
                    ),
                }
            ]
        }

    @tool(
        "submit_booking_draft",
        "Record a booking draft's field values once a human has filled in and submitted the "
        "booking form inside its MCP App. Call this when the form's own submit handler "
        "fires, and only then -- it is view-initiated only, never called on the model's "
        "initiative, which is why it does not appear in the model's tool list. Call it "
        "exactly once per form submission, keyed by booking_draft_id, so a retried request "
        "stays idempotent.",
        strict_schema(
            {
                "booking_draft_id": {"type": "string"},
                "form_fields": {
                    "type": "object",
                    "description": "The submitted form's field values, as entered by the user.",
                },
            },
        ),
    )
    async def submit_booking_draft(args: dict[str, Any]) -> dict[str, Any]:
        draft_id = args["booking_draft_id"]
        # Keyed by the view-generated id, not appended to -- a retried submit (double-click,
        # a flaky RPC retry) overwrites the same draft instead of creating a second one.
        _booking_drafts[draft_id] = {
            "session_id": session_id,
            "form_fields": args.get("form_fields", {}),
        }
        return {"content": [{"type": "text", "text": f"Booking draft {draft_id} recorded."}]}

    @tool(
        "mint_gesture_token",
        "Mint a short-lived, single-use token proving the checkout App's pay button was just "
        "clicked by a real person, and hand it back so the same click can immediately call "
        "confirm_booking with it. Call this when the checkout view's own click handler has "
        "just verified the click event is trusted, and only then, never speculatively -- the "
        "token expires 30 seconds after minting and is consumed on first use "
        f"({GESTURE_TOKEN_TTL_SECONDS}s window). This never appears in the model's tool list "
        "and is never called from agent code (CONSTITUTION I.2, layer 3).",
        strict_schema({"booking_draft_id": {"type": "string"}}),
    )
    async def mint_gesture_token(args: dict[str, Any]) -> dict[str, Any]:
        draft_id = args["booking_draft_id"]
        if booking_draft(draft_id) is None:
            return _error_result(f"no booking draft {draft_id!r}")
        token = gesture_tokens.mint(draft_id)
        return _text_result(
            {"gesture_token": token, "expires_in_seconds": GESTURE_TOKEN_TTL_SECONDS}
        )

    @tool(
        "confirm_booking",
        "Confirm a booking and trigger the mock payment gateway -- the last, irreversible "
        "step in the flow. This tool is invisible to the model by design (CONSTITUTION I.2) "
        "and fires only from a trusted browser click event carrying a gesture token minted "
        "at that moment; there is no reasoning path or tool-call sequence that reaches it "
        "from the conversation side. Call this when the checkout view's own confirm button "
        "fires, and only then -- never from agent code.",
        strict_schema(
            {
                "booking_draft_id": {"type": "string"},
                "gesture_token": {
                    "type": "string",
                    "description": "Minted by mint_gesture_token on a trusted click; rejected "
                    "if absent, unknown, minted for a different draft, or older than "
                    f"{GESTURE_TOKEN_TTL_SECONDS} seconds.",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Client-generated, unique per payment attempt. A retried "
                    "call with the same key returns the original attempt's result unchanged "
                    "instead of charging a second time.",
                },
                "payment_method": _payment_method_schema(),
                "financing": _financing_schema(),
            },
        ),
    )
    async def confirm_booking(args: dict[str, Any]) -> dict[str, Any]:
        draft_id = args["booking_draft_id"]
        ok, reason = gesture_tokens.consume(args["gesture_token"], booking_draft_id=draft_id)
        if not ok:
            return _error_result(f"confirm_booking rejected: {reason}")

        draft = booking_draft(draft_id)
        if draft is None:
            return _error_result(f"no booking draft {draft_id!r}")
        form_fields = draft.get("form_fields", {})
        session_uuid_ = session_ref_to_uuid(draft.get("session_id") or session_id)
        idempotency_key = args["idempotency_key"]
        financing_args = args.get("financing")

        try:
            listing_id, quote = await _price_draft(active_store, form_fields)
        except (_CheckoutInputError, KeyError, ListingNotFoundError, QuoteNotAvailableError) as exc:
            return _error_result(str(exc))
        server_monthly = _server_monthly_payment(quote.total, financing_args)

        existing = await active_bookings.find_by_idempotency_key(session_uuid_, idempotency_key)
        if existing is not None:
            return _text_result(_booking_response(existing, server_monthly_payment=server_monthly))

        now = datetime.now(UTC)
        customer = Customer(
            full_name=form_fields.get("name") or "Unknown",
            email=form_fields.get("email") or "unknown@example.invalid",
            phone=form_fields.get("phone") or None,
        )
        window = None
        if (
            form_fields.get("offer_type") == OfferType.RENT.value
            and form_fields.get("window_start")
            and form_fields.get("window_end")
        ):
            window = DateRange(start=form_fields["window_start"], end=form_fields["window_end"])

        submit_entry = new_audit_entry(
            actor="user",
            from_state=BookingState.DRAFT,
            event=BookingEvent.SUBMIT,
            event_id=idempotency_key,
            now=now,
            note="checkout confirmed by a trusted click",
        )
        fresh = Booking(
            id=uuid.uuid4(),
            session_id=session_uuid_,
            listing_id=listing_id,
            state=submit_entry.to_state,
            customer=customer,
            window=window,
            total=quote.total,
            idempotency_key=idempotency_key,
            audit=(submit_entry,),
            created_at=now,
            updated_at=now,
        )
        inserted = await active_bookings.insert(fresh)
        if inserted.id != fresh.id:
            # A concurrent confirm_booking call already claimed this idempotency key -- don't
            # authorise a second time (that would risk a double charge); report back whatever
            # that other call has produced so far.
            return _text_result(_booking_response(inserted, server_monthly_payment=server_monthly))

        try:
            outcome_hint = PaymentOutcome(args["payment_method"]["simulated_outcome"])
        except ValueError:
            return _error_result(
                f"unknown simulated_outcome {args['payment_method']['simulated_outcome']!r}"
            )
        intent = PaymentIntent(
            amount=quote.total,
            last4=args["payment_method"]["last4"],
            outcome_hint=outcome_hint,
            idempotency_key=idempotency_key,
        )
        auth = await active_gateway.authorise(intent, idem=idempotency_key)

        now2 = datetime.now(UTC)
        if auth.outcome.is_success:
            await active_gateway.capture(auth.auth_id or "", idem=idempotency_key)
            transition_entry = new_audit_entry(
                actor="system",
                from_state=BookingState.PENDING,
                event=BookingEvent.AUTHORISE,
                event_id=auth.auth_id or idempotency_key,
                now=now2,
                note=auth.outcome.value,
            )
        else:
            transition_entry = new_audit_entry(
                actor="system",
                from_state=BookingState.PENDING,
                event=BookingEvent.DECLINE,
                event_id=idempotency_key,
                now=now2,
                note=auth.outcome.value,
            )
        updated = inserted.with_transition(transition_entry, now=now2)
        await active_bookings.update(updated)

        return _text_result(_booking_response(updated, server_monthly_payment=server_monthly))

    return [
        ToolSpec(open_booking_form, MODEL_AND_APP),
        ToolSpec(open_checkout, MODEL_AND_APP),
        ToolSpec(submit_booking_draft, APP_ONLY),
        ToolSpec(mint_gesture_token, APP_ONLY),
        ToolSpec(confirm_booking, APP_ONLY),
    ]
