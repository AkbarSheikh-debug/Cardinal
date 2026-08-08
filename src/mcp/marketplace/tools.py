"""The five `marketplace-mcp` tools (PHASE-2 §4).

Every handler closes over a `ListingStore` and searches or fetches across *every*
registered source at once -- `search_cars` and `compare_listings` never take a marketplace
name as input, because the model is not supposed to know marketplaces are plural
(CONSTITUTION II.6). `check_availability` and `get_quote` need adapter-specific pricing and
booking logic, so they route through `adapter_by_name` once they know which source a
listing came from.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import ToolAnnotations, tool

from src.adapters.protocol import ListingNotFoundError, QuoteNotAvailableError
from src.adapters.registry import adapter_by_name, registered_source_names
from src.adapters.store import ListingStore
from src.domain.dates import DateRange
from src.domain.enums import FuelType, OfferType, Transmission, VehicleCategory
from src.domain.listing import ListingSummary
from src.domain.marketplace import (
    MAX_PAGE_SIZE,
    QuoteTerms,
    SearchPage,
    SearchQuery,
    SortKey,
)
from src.domain.trust import wrap_listing_content
from src.mcp.audience import MODEL_AND_APP, ToolSpec
from src.mcp.schema import enum_array_property, enum_property, strict_schema

READ_ONLY = ToolAnnotations(readOnlyHint=True)

_MAX_COMPARE_ITEMS = 5


def _text_result(payload: Any) -> dict[str, Any]:
    import json

    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def _error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


def _listing_ref_properties() -> dict[str, Any]:
    return {
        "source": enum_property(
            registered_source_names(), description="Which marketplace this listing came from."
        ),
        "source_id": {
            "type": "string",
            "description": "That marketplace's own id for the listing, e.g. 'AB-4471'.",
        },
    }


def _listing_ref_schema() -> dict[str, Any]:
    """Nested `{source, source_id}` shape, e.g. one entry in compare_listings' `items` array.

    Deliberately not run through `strict_schema` -- gate 2.3 checks the *top-level* schema of
    each tool, and an array-item schema carrying its own `strict` flag would be a category
    error (strictness is a property of a tool's whole parameter set, not of one nested shape).
    """
    return {
        "type": "object",
        "properties": _listing_ref_properties(),
        "required": ["source", "source_id"],
        "additionalProperties": False,
    }


def build_tool_specs(store: ListingStore) -> list[ToolSpec]:
    """One `ToolSpec` per marketplace-mcp tool, closed over `store`."""

    # -- search_cars ------------------------------------------------------------------

    @tool(
        "search_cars",
        "Search across every registered car marketplace at once and return lightweight "
        "summaries, never full records -- results are capped at 20 per page. Call this "
        "when the user has stated at least one concrete requirement (a budget, a category, "
        "a brand, a date they need the car by, or a buy-versus-rent preference), never "
        "speculatively on a turn where nothing new is known. Use get_listing on a specific "
        "id once the user shows interest in it rather than pulling every candidate's full "
        "record up front, and use compare_listings instead of five separate get_listing "
        "calls once the user has a short list.",
        strict_schema(
            {
                "categories": enum_array_property(
                    tuple(c.value for c in VehicleCategory),
                    description="Restrict to these vehicle categories. Omit for no restriction.",
                ),
                "brands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict to these exact brand names. Omit for no restriction.",
                },
                "fuel_types": enum_array_property(
                    tuple(f.value for f in FuelType),
                    description="Restrict to these fuel types. Omit for no restriction.",
                ),
                "transmissions": enum_array_property(
                    tuple(t.value for t in Transmission),
                    description="Restrict to these transmission types. Omit for no restriction.",
                ),
                "offer_type": enum_property(
                    tuple(o.value for o in OfferType),
                    description="'buy', 'rent', or 'both'. Omit for either.",
                ),
                "max_price_eur": {
                    "type": "number",
                    "description": "Maximum purchase price in EUR. Excludes rent-only listings.",
                },
                "max_rental_daily_eur": {
                    "type": "number",
                    "description": "Maximum daily rental rate in EUR.",
                },
                "max_mileage_km": {"type": "integer", "minimum": 0},
                "min_year": {"type": "integer", "minimum": 1990},
                "min_seats": {"type": "integer", "minimum": 2, "maximum": 9},
                "available_from": {
                    "type": "string",
                    "description": "ISO date. Must be given together with available_to.",
                },
                "available_to": {
                    "type": "string",
                    "description": "ISO date. Must be given together with available_from.",
                },
                "sort": enum_property(
                    tuple(s.value for s in SortKey),
                    description="Sort order. Defaults to price ascending.",
                ),
                "page": {"type": "integer", "minimum": 1, "description": "Defaults to 1."},
                "page_size": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_PAGE_SIZE,
                    "description": f"Defaults to {MAX_PAGE_SIZE}, the hard cap.",
                },
            },
            required=[],
        ),
        annotations=READ_ONLY,
    )
    async def search_cars(args: dict[str, Any]) -> dict[str, Any]:
        try:
            query = _build_search_query(args)
        except ValueError as exc:
            return _error_result(str(exc))
        listings, total = await store.query(query, sources=registered_source_names())
        page = SearchPage(
            items=tuple(ListingSummary.from_listing(item) for item in listings),
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
        return _text_result(page.model_dump(mode="json"))

    # -- get_listing --------------------------------------------------------------------

    @tool(
        "get_listing",
        "Fetch the complete record for one listing, identified by the marketplace "
        "('source') and that marketplace's own id ('source_id') as returned by search_cars "
        "or compare_listings. Call this when the user asks about detail a search summary "
        "does not carry -- full specification, depreciation curve, powertrain, insurance "
        "band. Do not call it for every row of a search result; that defeats the summary "
        "cap and will blow the session's token budget over a long conversation.",
        strict_schema(_listing_ref_properties(), required=["source", "source_id"]),
        annotations=READ_ONLY,
    )
    async def get_listing(args: dict[str, Any]) -> dict[str, Any]:
        listing = await store.fetch(args["source"], args["source_id"])
        if listing is None:
            return _error_result(f"no listing {args['source_id']!r} on {args['source']!r}")
        # CONSTITUTION I.4 / gate 10.4: this is the only tool that ever returns a listing's
        # full, untrusted `description` -- search_cars' summaries never carry it at all
        # (`ListingSummary`'s own docstring). Replacing the raw field with the wrapped,
        # labelled form here means every caller (the orchestrator and every subagent that
        # holds `get_listing`) sees it wrapped, with no second call site to remember.
        payload = listing.model_dump(mode="json")
        payload["description"] = wrap_listing_content(listing)
        return _text_result(payload)

    # -- check_availability ---------------------------------------------------------------

    @tool(
        "check_availability",
        "Check whether a specific listing can be picked up, rented, or collected across a "
        "date range. Call this when the user has named or implied travel or ownership dates "
        "and is deciding between two or more candidates, or immediately before opening a "
        "booking flow for a rental. A dealer listing always reports available across the "
        "whole window; a rental listing reports the real free sub-ranges, which may be "
        "empty or only partially free.",
        strict_schema(
            {
                "source": enum_property(registered_source_names(), description="Marketplace."),
                "source_id": {
                    "type": "string",
                    "description": "The listing's id on that marketplace.",
                },
                "window_start": {"type": "string", "description": "ISO date, inclusive."},
                "window_end": {"type": "string", "description": "ISO date, inclusive."},
            },
            required=["source", "source_id", "window_start", "window_end"],
        ),
    )
    async def check_availability(args: dict[str, Any]) -> dict[str, Any]:
        try:
            window = DateRange(start=args["window_start"], end=args["window_end"])
        except ValueError as exc:
            return _error_result(str(exc))
        try:
            adapter = adapter_by_name(store, args["source"])
            result = await adapter.availability(args["source_id"], window)
        except (ListingNotFoundError, KeyError) as exc:
            return _error_result(str(exc))
        return _text_result(result.model_dump(mode="json"))

    # -- get_quote ------------------------------------------------------------------------

    @tool(
        "get_quote",
        "Price one listing under specific terms -- a purchase, or a rental across a date "
        "window -- and return an itemised breakdown the user can be shown verbatim. Call "
        "this when the user is comparing real total price rather than list price, typically "
        "after narrowing to a short list and wanting the number including fees, insurance "
        "and excess-mileage charges. A rental quote requires window_start and window_end; "
        "omit both for a purchase quote.",
        strict_schema(
            {
                "source": enum_property(registered_source_names(), description="Marketplace."),
                "source_id": {
                    "type": "string",
                    "description": "The listing's id on that marketplace.",
                },
                "window_start": {
                    "type": "string",
                    "description": "ISO date. Required for a rental quote; omit for a purchase.",
                },
                "window_end": {
                    "type": "string",
                    "description": "ISO date, paired with window_start.",
                },
                "expected_km_per_day": {"type": "integer", "minimum": 0},
                "include_insurance": {"type": "boolean", "description": "Defaults to true."},
                "trade_in_value_eur": {
                    "type": "number",
                    "description": "Purchase path only: a trade-in allowance to deduct.",
                },
            },
            required=["source", "source_id"],
        ),
    )
    async def get_quote(args: dict[str, Any]) -> dict[str, Any]:
        try:
            terms = _build_quote_terms(args)
        except ValueError as exc:
            return _error_result(str(exc))
        try:
            adapter = adapter_by_name(store, args["source"])
            quote = await adapter.quote(args["source_id"], terms)
        except (ListingNotFoundError, QuoteNotAvailableError, KeyError) as exc:
            return _error_result(str(exc))
        return _text_result(quote.model_dump(mode="json"))

    # -- compare_listings -----------------------------------------------------------------

    @tool(
        "compare_listings",
        "Align up to five listings side by side on the same fields -- price, mileage, year, "
        "fuel, category, and projected residual value -- so the result can be rendered as a "
        "comparison table without five separate get_listing round trips. Call this when the "
        "user is deciding between a short list of specific cars they have already "
        "identified, not as a substitute for search_cars. Passing more than five ids is "
        "rejected; narrow the list first.",
        strict_schema(
            {
                "items": {
                    "type": "array",
                    "items": _listing_ref_schema(),
                    "minItems": 2,
                    "maxItems": _MAX_COMPARE_ITEMS,
                    "description": "2 to 5 listings to align, each {source, source_id}.",
                },
            },
        ),
        annotations=READ_ONLY,
    )
    async def compare_listings(args: dict[str, Any]) -> dict[str, Any]:
        items = args["items"]
        if len(items) > _MAX_COMPARE_ITEMS:
            return _error_result(f"at most {_MAX_COMPARE_ITEMS} listings; got {len(items)}")
        listings = []
        for ref in items:
            listing = await store.fetch(ref["source"], ref["source_id"])
            if listing is None:
                return _error_result(f"no listing {ref['source_id']!r} on {ref['source']!r}")
            listings.append(listing)

        def row(getter: Any) -> dict[str, Any]:
            return {listing.source_id: getter(listing) for listing in listings}

        matrix = {
            "brand": row(lambda item: item.brand),
            "model": row(lambda item: item.model),
            "year": row(lambda item: item.year),
            "category": row(lambda item: item.category.value),
            "offer_type": row(lambda item: item.offer_type.value),
            "price_buy_eur": row(
                lambda item: str(item.price_buy.amount) if item.price_buy else None
            ),
            "rental_daily_eur": row(
                lambda item: str(item.rental_rates.daily.amount) if item.rental_rates else None
            ),
            "mileage_km": row(lambda item: item.mileage_km),
            "fuel_type": row(lambda item: item.fuel_type.value),
            "transmission": row(lambda item: item.transmission.value),
            "insurance_band": row(lambda item: item.insurance_band),
            "residual_value_3y_eur": row(lambda item: str(item.residual_value(3).amount)),
        }
        return _text_result({"compared": [item.source_id for item in listings], "fields": matrix})

    return [
        ToolSpec(search_cars, MODEL_AND_APP),
        ToolSpec(get_listing, MODEL_AND_APP),
        ToolSpec(check_availability, MODEL_AND_APP),
        ToolSpec(get_quote, MODEL_AND_APP),
        ToolSpec(compare_listings, MODEL_AND_APP),
    ]


def _build_search_query(args: dict[str, Any]) -> SearchQuery:
    kwargs: dict[str, Any] = {}
    if categories := args.get("categories"):
        kwargs["categories"] = tuple(VehicleCategory(c) for c in categories)
    if brands := args.get("brands"):
        kwargs["brands"] = tuple(brands)
    if fuel_types := args.get("fuel_types"):
        kwargs["fuel_types"] = tuple(FuelType(f) for f in fuel_types)
    if transmissions := args.get("transmissions"):
        kwargs["transmissions"] = tuple(Transmission(t) for t in transmissions)
    if offer_type := args.get("offer_type"):
        kwargs["offer_type"] = OfferType(offer_type)
    if (max_price := args.get("max_price_eur")) is not None:
        from src.domain.money import Money

        kwargs["max_price"] = Money.of(str(max_price))
    if (max_rental := args.get("max_rental_daily_eur")) is not None:
        from src.domain.money import Money

        kwargs["max_rental_daily"] = Money.of(str(max_rental))
    if (v := args.get("max_mileage_km")) is not None:
        kwargs["max_mileage_km"] = v
    if (v := args.get("min_year")) is not None:
        kwargs["min_year"] = v
    if (v := args.get("min_seats")) is not None:
        kwargs["min_seats"] = v

    start, end = args.get("available_from"), args.get("available_to")
    if (start is None) != (end is None):
        raise ValueError("available_from and available_to must be given together")
    if start is not None and end is not None:
        kwargs["available_between"] = DateRange(start=start, end=end)

    if sort := args.get("sort"):
        kwargs["sort"] = SortKey(sort)
    if (v := args.get("page")) is not None:
        kwargs["page"] = v
    if (v := args.get("page_size")) is not None:
        # The schema's own `maximum: MAX_PAGE_SIZE` already rejects an oversized value
        # before this handler runs -- nothing above MAX_PAGE_SIZE ever reaches here.
        kwargs["page_size"] = v

    return SearchQuery(**kwargs)


def _build_quote_terms(args: dict[str, Any]) -> QuoteTerms:
    kwargs: dict[str, Any] = {}
    start, end = args.get("window_start"), args.get("window_end")
    if (start is None) != (end is None):
        raise ValueError("window_start and window_end must be given together")
    if start is not None and end is not None:
        kwargs["window"] = DateRange(start=start, end=end)
    if (v := args.get("expected_km_per_day")) is not None:
        kwargs["expected_km_per_day"] = v
    if (v := args.get("include_insurance")) is not None:
        kwargs["include_insurance"] = v
    if (v := args.get("trade_in_value_eur")) is not None:
        from src.domain.money import Money

        kwargs["trade_in_value"] = Money.of(str(v))
    return QuoteTerms(**kwargs)
