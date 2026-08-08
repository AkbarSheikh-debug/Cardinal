"""`booking-mcp` visibility and contract stubs (PHASE-2 §4, CONSTITUTION I.2), plus PHASE-7's
`open_booking_form`/`submit_booking_draft`/`ui://booking/form` and PHASE-8's
`open_checkout`/`mint_gesture_token`/`confirm_booking`/`ui://checkout/payment`.

Gate 2.6 proves visibility at the phase level; gate 7/8 prove the resource/host mechanics and
the payment lifecycle end-to-end through a real browser. These tests pin the unit-level
behaviour so a regression fails on the next `make test`, not just on the next `make gate`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from mcp import types as mcp_types
from src.adapters.booking_store import InMemoryBookingStore, session_ref_to_uuid
from src.adapters.registry import adapter_by_name
from src.adapters.store import InMemoryListingStore
from src.domain.enums import OfferType
from src.domain.financing import FinancingTerms, compute_monthly_payment
from src.domain.listing import Listing
from src.domain.marketplace import QuoteTerms
from src.mcp.audience import resolved_tool_names
from src.mcp.booking.gesture import GESTURE_TOKEN_TTL_SECONDS, GestureTokenStore
from src.mcp.booking.resources import BOOKING_FORM_URI, CHECKOUT_URI
from src.mcp.booking.server import build_booking_server
from src.mcp.booking.tools import booking_draft
from src.mcp.ui.sink import NullUISink
from tests.conftest import call_mcp_tool

APP_ONLY_TOOLS = {"submit_booking_draft", "mint_gesture_token", "confirm_booking"}
MODEL_VISIBLE_TOOLS = {"open_booking_form", "open_checkout"}


def _buyable(catalogue: tuple[Listing, ...]) -> Listing:
    """Exactly `OfferType.BUY`, not `BOTH` -- so `form_fields["offer_type"]` is deterministically
    `"buy"` for every assertion below rather than sometimes `"both"`.
    """
    return next(
        item
        for item in catalogue
        if item.source == "mock_autobazaar" and item.offer_type is OfferType.BUY
    )


def _rentable(catalogue: tuple[Listing, ...]) -> Listing:
    return next(
        item
        for item in catalogue
        if item.source == "mock_drivenow" and item.offer_type is OfferType.RENT
    )


async def _submit_draft(
    *, store: InMemoryListingStore, session_id: str, draft_id: str, listing: Listing, **extra: Any
) -> None:
    config = build_booking_server(audience="app", session_id=session_id, store=store)
    args = {
        "source": listing.source,
        "source_id": listing.source_id,
        "offer_type": listing.offer_type.value,
        **extra,
    }
    result = await call_mcp_tool(
        config["instance"],
        "submit_booking_draft",
        {"booking_draft_id": draft_id, "form_fields": args},
    )
    assert not result.isError


async def _mint_token(*, store: InMemoryListingStore, session_id: str, draft_id: str) -> str:
    config = build_booking_server(audience="app", session_id=session_id, store=store)
    result = await call_mcp_tool(
        config["instance"], "mint_gesture_token", {"booking_draft_id": draft_id}
    )
    assert not result.isError
    payload = json.loads(result.content[0].text)
    return str(payload["gesture_token"])


# -- visibility ------------------------------------------------------------------------------


async def test_model_facing_server_never_resolves_app_only_tools() -> None:
    names = set(await resolved_tool_names(build_booking_server(audience="model")))
    assert names == MODEL_VISIBLE_TOOLS
    assert not (names & APP_ONLY_TOOLS)


async def test_app_facing_server_resolves_every_tool() -> None:
    names = set(await resolved_tool_names(build_booking_server(audience="app")))
    assert names == MODEL_VISIBLE_TOOLS | APP_ONLY_TOOLS


async def test_confirm_booking_is_unreachable_on_the_model_build() -> None:
    server_instance = build_booking_server(audience="model")["instance"]
    result = await call_mcp_tool(
        server_instance, "confirm_booking", {"booking_draft_id": "draft-1", "gesture_token": "tok"}
    )
    assert result.isError
    assert "not found" in result.content[0].text.lower() or "Tool" in result.content[0].text


async def test_confirm_booking_rejects_a_token_it_never_minted() -> None:
    """It is hidden from the model, not broken -- the app side still has to work, and its
    first line of defence (a real gesture token) still applies even when called directly.
    """
    server_instance = build_booking_server(audience="app")["instance"]
    result = await call_mcp_tool(
        server_instance,
        "confirm_booking",
        {
            "booking_draft_id": "draft-never-existed",
            "gesture_token": "not-a-real-token",
            "idempotency_key": "test-key-00000001",
            "payment_method": {"last4": "4242", "simulated_outcome": "success"},
            "financing": None,
        },
    )
    assert result.isError
    assert "confirm_booking rejected" in result.content[0].text


# -- open_booking_form / submit_booking_draft (PHASE-7) ---------------------------------------


async def test_open_booking_form_pushes_a_mount_app_message_through_the_sink() -> None:
    sink = NullUISink()
    config = build_booking_server(audience="model", session_id="t1", sink=sink)
    args = {"source": "mock_autobazaar", "source_id": "AB-1", "offer_type": "buy"}
    result = await call_mcp_tool(config["instance"], "open_booking_form", args)

    assert not result.isError
    assert len(sink.pushed) == 1
    message = sink.pushed[0]
    assert message == {
        "kind": "mcp_app_open",
        "resourceUri": BOOKING_FORM_URI,
        "toolName": "open_booking_form",
        "toolInput": args,
    }


async def test_submit_booking_draft_is_idempotent_per_draft_id() -> None:
    config = build_booking_server(audience="app", session_id="t2")
    server_instance = config["instance"]
    first = await call_mcp_tool(
        server_instance,
        "submit_booking_draft",
        {"booking_draft_id": "d-1", "form_fields": {"name": "Jane"}},
    )
    assert not first.isError
    assert booking_draft("d-1") == {"session_id": "t2", "form_fields": {"name": "Jane"}}

    # A retried submit with the same id overwrites, not duplicates.
    await call_mcp_tool(
        server_instance,
        "submit_booking_draft",
        {"booking_draft_id": "d-1", "form_fields": {"name": "Jane Doe"}},
    )
    assert booking_draft("d-1") == {"session_id": "t2", "form_fields": {"name": "Jane Doe"}}


# -- resources --------------------------------------------------------------------------------


async def test_both_resources_are_registered_with_declared_csp() -> None:
    config = build_booking_server(audience="model")
    server_instance = config["instance"]

    list_handler = server_instance.request_handlers[mcp_types.ListResourcesRequest]
    listed = await list_handler(None)
    resources = {str(r.uri): r for r in listed.root.resources}
    assert set(resources) == {BOOKING_FORM_URI, CHECKOUT_URI}
    for resource in resources.values():
        assert resource.mimeType == "text/html;profile=mcp-app"
        assert resource.meta == {"ui": {"csp": {"connectDomains": []}, "prefersBorder": True}}

    read_handler = server_instance.request_handlers[mcp_types.ReadResourceRequest]
    for uri, expect_substring in (
        (BOOKING_FORM_URI, "ui/initialize"),
        (CHECKOUT_URI, "MOCK"),
    ):
        read_request = mcp_types.ReadResourceRequest(
            params=mcp_types.ReadResourceRequestParams(uri=mcp_types.AnyUrl(uri))
        )
        read_result = await read_handler(read_request)
        contents = read_result.root.contents
        assert len(contents) == 1
        assert contents[0].mimeType == "text/html;profile=mcp-app"
        assert expect_substring in contents[0].text
        assert contents[0].meta == {"ui": {"csp": {"connectDomains": []}, "prefersBorder": True}}


# -- open_checkout (PHASE-8) --------------------------------------------------------------------


async def test_open_checkout_prices_the_draft_from_the_real_listing_and_mounts_the_app(
    catalogue: tuple[Listing, ...], store: InMemoryListingStore
) -> None:
    listing = _buyable(catalogue)
    session_id = "checkout-open-1"
    await _submit_draft(store=store, session_id=session_id, draft_id="oc-1", listing=listing)

    sink = NullUISink()
    config = build_booking_server(audience="app", session_id=session_id, sink=sink, store=store)
    result = await call_mcp_tool(config["instance"], "open_checkout", {"booking_draft_id": "oc-1"})
    assert not result.isError

    assert len(sink.pushed) == 1
    message = sink.pushed[0]
    assert message["kind"] == "mcp_app_open"
    assert message["resourceUri"] == CHECKOUT_URI
    assert message["toolInput"]["source_id"] == listing.source_id
    assert message["toolInput"]["offer_type"] == "buy"
    adapter = adapter_by_name(store, listing.source)
    expected_quote = await adapter.quote(listing.source_id, QuoteTerms())
    assert Decimal(message["toolInput"]["total_amount"]) == expected_quote.total.amount


async def test_open_checkout_errors_on_an_unknown_draft() -> None:
    config = build_booking_server(audience="app", session_id="checkout-open-2")
    result = await call_mcp_tool(
        config["instance"], "open_checkout", {"booking_draft_id": "no-such-draft"}
    )
    assert result.isError


# -- mint_gesture_token -------------------------------------------------------------------------


async def test_mint_gesture_token_requires_an_existing_draft() -> None:
    config = build_booking_server(audience="app", session_id="gt-1")
    result = await call_mcp_tool(
        config["instance"], "mint_gesture_token", {"booking_draft_id": "no-such-draft"}
    )
    assert result.isError


def test_gesture_token_store_rejects_unknown_missing_mismatched_and_stale_tokens() -> None:
    store = GestureTokenStore()
    token = store.mint("draft-a")

    ok, _ = store.consume("does-not-exist", booking_draft_id="draft-a")
    assert ok is False

    token2 = store.mint("draft-b")
    ok, reason = store.consume(token2, booking_draft_id="draft-a")
    assert ok is False
    assert "different booking draft" in reason

    # Single-use: consuming the *right* token for the *right* draft succeeds once...
    ok, _ = store.consume(token, booking_draft_id="draft-a")
    assert ok is True
    # ...and a second attempt with the same token fails, even though nothing else changed.
    ok, _ = store.consume(token, booking_draft_id="draft-a")
    assert ok is False

    stale_token = store.mint("draft-c")
    store._tokens[stale_token].minted_at -= GESTURE_TOKEN_TTL_SECONDS + 1
    ok, reason = store.consume(stale_token, booking_draft_id="draft-c")
    assert ok is False
    assert "expired" in reason


# -- confirm_booking (PHASE-8) ------------------------------------------------------------------


async def test_confirm_booking_success_card_confirms_the_booking(
    catalogue: tuple[Listing, ...], store: InMemoryListingStore
) -> None:
    listing = _buyable(catalogue)
    session_id = "confirm-success-1"
    draft_id = "cb-success-1"
    await _submit_draft(store=store, session_id=session_id, draft_id=draft_id, listing=listing)
    token = await _mint_token(store=store, session_id=session_id, draft_id=draft_id)

    config = build_booking_server(audience="app", session_id=session_id, store=store)
    result = await call_mcp_tool(
        config["instance"],
        "confirm_booking",
        {
            "booking_draft_id": draft_id,
            "gesture_token": token,
            "idempotency_key": "confirm-key-success-1",
            "payment_method": {"last4": "4242", "simulated_outcome": "success"},
            "financing": None,
        },
    )
    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["state"] == "confirmed"
    assert payload["outcome"] == "success"
    assert payload["booking_id"]


@pytest.mark.parametrize(
    "outcome",
    [
        "declined_insufficient_funds",
        "declined_expired_card",
        "gateway_error",
        "timeout",
    ],
)
async def test_confirm_booking_every_decline_outcome_fails_the_booking(
    outcome: str, catalogue: tuple[Listing, ...], store: InMemoryListingStore
) -> None:
    listing = _buyable(catalogue)
    session_id = f"confirm-decline-{outcome}"
    draft_id = f"cb-{outcome}"
    await _submit_draft(store=store, session_id=session_id, draft_id=draft_id, listing=listing)
    token = await _mint_token(store=store, session_id=session_id, draft_id=draft_id)

    config = build_booking_server(audience="app", session_id=session_id, store=store)
    result = await call_mcp_tool(
        config["instance"],
        "confirm_booking",
        {
            "booking_draft_id": draft_id,
            "gesture_token": token,
            "idempotency_key": f"confirm-key-{outcome}",
            "payment_method": {"last4": "0002", "simulated_outcome": outcome},
            "financing": None,
        },
    )
    assert not result.isError  # a decline is a business outcome, not a tool error
    payload = json.loads(result.content[0].text)
    assert payload["state"] == "failed"
    assert payload["outcome"] == outcome


async def test_confirm_booking_double_submit_same_idempotency_key_is_one_booking(
    catalogue: tuple[Listing, ...], store: InMemoryListingStore
) -> None:
    """Gate 8.5: a retried confirm_booking with the same idempotency key produces one
    booking and two identical responses, not two bookings.
    """
    listing = _buyable(catalogue)
    session_id = "confirm-double-1"
    draft_id = "cb-double-1"
    bookings = InMemoryBookingStore()
    await _submit_draft(store=store, session_id=session_id, draft_id=draft_id, listing=listing)

    async def _confirm() -> dict[str, Any]:
        token = await _mint_token(store=store, session_id=session_id, draft_id=draft_id)
        config = build_booking_server(
            audience="app", session_id=session_id, store=store, booking_store=bookings
        )
        result = await call_mcp_tool(
            config["instance"],
            "confirm_booking",
            {
                "booking_draft_id": draft_id,
                "gesture_token": token,
                "idempotency_key": "confirm-key-double-1",
                "payment_method": {"last4": "4242", "simulated_outcome": "success"},
                "financing": None,
            },
        )
        assert not result.isError
        return json.loads(result.content[0].text)  # type: ignore[no-any-return]

    first = await _confirm()
    second = await _confirm()
    assert first == second

    session_uuid_ = session_ref_to_uuid(session_id)
    existing = await bookings.find_by_idempotency_key(session_uuid_, "confirm-key-double-1")
    assert existing is not None
    assert str(existing.id) == first["booking_id"]


async def test_confirm_booking_financing_matches_domain_calculation(
    catalogue: tuple[Listing, ...], store: InMemoryListingStore
) -> None:
    """Gate 8.11's server-side half: the figure `confirm_booking` returns is exactly what
    `compute_monthly_payment` produces from the same authoritative total and terms.
    """
    listing = _buyable(catalogue)
    session_id = "confirm-financing-1"
    draft_id = "cb-financing-1"
    await _submit_draft(store=store, session_id=session_id, draft_id=draft_id, listing=listing)
    token = await _mint_token(store=store, session_id=session_id, draft_id=draft_id)

    financing_args = {"term_months": 60, "down_payment_pct": 10, "apr_pct": 6.9}
    config = build_booking_server(audience="app", session_id=session_id, store=store)
    result = await call_mcp_tool(
        config["instance"],
        "confirm_booking",
        {
            "booking_draft_id": draft_id,
            "gesture_token": token,
            "idempotency_key": "confirm-key-financing-1",
            "payment_method": {"last4": "4242", "simulated_outcome": "success"},
            "financing": financing_args,
        },
    )
    assert not result.isError
    payload = json.loads(result.content[0].text)

    adapter = adapter_by_name(store, listing.source)
    expected_quote = await adapter.quote(listing.source_id, QuoteTerms())
    terms = FinancingTerms(term_months=60, down_payment_pct=Decimal(10), apr_pct=Decimal("6.9"))
    expected = compute_monthly_payment(expected_quote.total, terms)
    assert payload["server_monthly_payment_eur"] == str(expected.amount)


async def test_confirm_booking_rental_prices_the_window(
    catalogue: tuple[Listing, ...], store: InMemoryListingStore
) -> None:
    listing = _rentable(catalogue)
    session_id = "confirm-rental-1"
    draft_id = "cb-rental-1"
    await _submit_draft(
        store=store,
        session_id=session_id,
        draft_id=draft_id,
        listing=listing,
        offer_type="rent",
        window_start="2026-09-01",
        window_end="2026-09-08",
    )
    token = await _mint_token(store=store, session_id=session_id, draft_id=draft_id)

    config = build_booking_server(audience="app", session_id=session_id, store=store)
    result = await call_mcp_tool(
        config["instance"],
        "confirm_booking",
        {
            "booking_draft_id": draft_id,
            "gesture_token": token,
            "idempotency_key": "confirm-key-rental-1",
            "payment_method": {"last4": "4242", "simulated_outcome": "success"},
            "financing": None,
        },
    )
    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["state"] == "confirmed"
