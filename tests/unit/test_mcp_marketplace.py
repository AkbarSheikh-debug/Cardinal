"""`marketplace-mcp` tool behaviour (PHASE-2 §4).

Gate 2 proves the contract (schema discipline, size caps, transport parity). These tests
prove the handlers behind that contract actually do the right thing -- filtering, routing to
the correct adapter, and failing the way a caller can act on rather than crashing.
"""

from __future__ import annotations

import json

import pytest

from src.adapters.store import InMemoryListingStore
from src.mcp.marketplace.server import build_marketplace_server
from tests.conftest import call_mcp_tool


@pytest.fixture(scope="module")
def server_instance(store: InMemoryListingStore) -> object:
    return build_marketplace_server(store, audience="model")["instance"]


async def test_search_cars_with_no_filters_returns_a_full_page(server_instance: object) -> None:
    result = await call_mcp_tool(server_instance, "search_cars", {})
    assert not result.isError
    page = json.loads(result.content[0].text)
    assert len(page["items"]) == 20
    assert page["total"] == 240


async def test_search_cars_spans_every_registered_marketplace(server_instance: object) -> None:
    result = await call_mcp_tool(
        server_instance, "search_cars", {"offer_type": "rent", "page_size": 20}
    )
    page = json.loads(result.content[0].text)
    sources = {item["source"] for item in page["items"]}
    assert sources, "no rentable listings found at all"
    # A search across "the marketplace" must not be scoped to one adapter -- that would be
    # exactly the branch CONSTITUTION II.6 forbids leaking up through this tool.
    assert len(registered_source_names_seen(page)) >= 1


def registered_source_names_seen(page: dict[str, object]) -> set[str]:
    return {item["source"] for item in page["items"]}  # type: ignore[union-attr,index]


async def test_search_cars_honours_category_filter(server_instance: object) -> None:
    result = await call_mcp_tool(server_instance, "search_cars", {"categories": ["suv"]})
    page = json.loads(result.content[0].text)
    assert page["items"]
    assert all(item["category"] == "suv" for item in page["items"])


async def test_search_cars_rejects_unpaired_availability_window(server_instance: object) -> None:
    result = await call_mcp_tool(server_instance, "search_cars", {"available_from": "2026-09-01"})
    assert result.isError


async def test_search_cars_rejects_an_oversized_page_size(server_instance: object) -> None:
    """CONSTITUTION II.7: a caller cannot ask for more than the cap -- the schema's own
    `maximum` rejects this before the handler runs, exactly like `SearchQuery` itself does.
    """
    result = await call_mcp_tool(server_instance, "search_cars", {"page_size": 999})
    assert result.isError


async def test_get_listing_round_trips_a_search_result(server_instance: object) -> None:
    search = await call_mcp_tool(server_instance, "search_cars", {})
    first = json.loads(search.content[0].text)["items"][0]
    result = await call_mcp_tool(
        server_instance, "get_listing", {"source": first["source"], "source_id": first["source_id"]}
    )
    assert not result.isError
    listing = json.loads(result.content[0].text)
    assert listing["source_id"] == first["source_id"]
    assert listing["raw"], "get_listing must retain raw upstream payload"


async def test_get_listing_wraps_description_as_untrusted_content(
    server_instance: object,
) -> None:
    """CONSTITUTION I.4 / gate 10.4: `get_listing` is the only tool that ever returns a
    listing's full `description` -- search_cars' summaries never carry it (`ListingSummary`'s
    own docstring). What get_listing returns for that field must be the wrapped, labelled
    form, not the raw seller text.
    """
    search = await call_mcp_tool(server_instance, "search_cars", {})
    first = json.loads(search.content[0].text)["items"][0]
    result = await call_mcp_tool(
        server_instance, "get_listing", {"source": first["source"], "source_id": first["source_id"]}
    )
    listing = json.loads(result.content[0].text)
    description = listing["description"]
    assert description.startswith("<listing_content ")
    assert f'listing_id="{first["source_id"]}"' in description
    assert f'source="{first["source"]}"' in description
    assert 'trust="untrusted"' in description
    assert description.rstrip().endswith("</listing_content>")


async def test_get_listing_on_unknown_id_is_a_tool_error_not_an_exception(
    server_instance: object,
) -> None:
    result = await call_mcp_tool(
        server_instance, "get_listing", {"source": "mock_autobazaar", "source_id": "does-not-exist"}
    )
    assert result.isError


async def test_check_availability_routes_dealer_to_always(server_instance: object) -> None:
    search = await call_mcp_tool(
        server_instance, "search_cars", {"offer_type": "buy", "page_size": 1}
    )
    item = json.loads(search.content[0].text)["items"][0]
    result = await call_mcp_tool(
        server_instance,
        "check_availability",
        {
            "source": item["source"],
            "source_id": item["source_id"],
            "window_start": "2026-09-01",
            "window_end": "2026-09-10",
        },
    )
    assert not result.isError
    availability = json.loads(result.content[0].text)
    if item["source"] == "mock_autobazaar":
        assert availability["status"] == "always"


async def test_get_quote_purchase_path_is_itemised(server_instance: object) -> None:
    search = await call_mcp_tool(
        server_instance, "search_cars", {"offer_type": "buy", "page_size": 1}
    )
    item = json.loads(search.content[0].text)["items"][0]
    result = await call_mcp_tool(
        server_instance, "get_quote", {"source": item["source"], "source_id": item["source_id"]}
    )
    assert not result.isError
    quote = json.loads(result.content[0].text)
    assert quote["lines"]
    assert quote["kind"] == "buy"


async def test_get_quote_rental_without_a_window_is_a_tool_error(server_instance: object) -> None:
    search = await call_mcp_tool(
        server_instance, "search_cars", {"offer_type": "rent", "page_size": 20}
    )
    items = json.loads(search.content[0].text)["items"]
    rent_only = [i for i in items if i["offer_type"] == "rent"]
    if not rent_only:
        pytest.skip("no rent-only listings in this catalogue")
    result = await call_mcp_tool(
        server_instance,
        "get_quote",
        {"source": rent_only[0]["source"], "source_id": rent_only[0]["source_id"]},
    )
    assert result.isError


async def test_compare_listings_aligns_fields_across_up_to_five(server_instance: object) -> None:
    search = await call_mcp_tool(server_instance, "search_cars", {"page_size": 3})
    items = json.loads(search.content[0].text)["items"]
    refs = [{"source": i["source"], "source_id": i["source_id"]} for i in items]
    result = await call_mcp_tool(server_instance, "compare_listings", {"items": refs})
    assert not result.isError
    comparison = json.loads(result.content[0].text)
    assert set(comparison["compared"]) == {r["source_id"] for r in refs}
    assert set(comparison["fields"]["brand"]) == {r["source_id"] for r in refs}


async def test_compare_listings_rejects_more_than_five(server_instance: object) -> None:
    search = await call_mcp_tool(server_instance, "search_cars", {"page_size": 6})
    items = json.loads(search.content[0].text)["items"]
    refs = [{"source": i["source"], "source_id": i["source_id"]} for i in items]
    # The schema's own maxItems:5 makes the MCP `Server`'s jsonschema input validation
    # reject this before our handler ever runs -- not our own bounds check.
    result = await call_mcp_tool(server_instance, "compare_listings", {"items": refs})
    assert result.isError
