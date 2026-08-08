"""`ui-mcp` tool handlers (PHASE-6): real bodies over the compiler, replacing P2's stubs.

Runs the tools through the real MCP `Server.request_handlers` (`call_mcp_tool`), the same
call path gate 2.6 already proved works, with a `NullUISink` standing in for the SSE
transport so what got "rendered" is inspectable in-process.
"""

from __future__ import annotations

import pytest

from src.adapters.store import InMemoryListingStore
from src.mcp.ui.server import build_ui_server
from src.mcp.ui.sink import NullUISink
from src.mcp.ui.surfaces import SurfaceRegistry
from tests.conftest import call_mcp_tool

EXPECTED_TOOLS = (
    "render_progress",
    "render_results",
    "render_detail",
    "render_tco",
    "compose_surface",
)


def _build(store: InMemoryListingStore | None = None) -> tuple[object, NullUISink, SurfaceRegistry]:
    sink = NullUISink()
    registry = SurfaceRegistry()
    config = build_ui_server(
        audience="model",
        session_id="test-session",
        sink=sink,
        registry=registry,
        store=store,
        phase=lambda: "interview",
    )
    return config["instance"], sink, registry


def test_every_ui_tool_is_registered(store: InMemoryListingStore) -> None:
    server_instance, _, _ = _build(store)
    from mcp import types as mcp_types

    async def _list() -> tuple[str, ...]:
        handler = server_instance.request_handlers[mcp_types.ListToolsRequest]
        result = await handler(None)
        return tuple(t.name for t in result.root.tools)

    import asyncio

    names = asyncio.run(_list())
    assert set(EXPECTED_TOOLS) <= set(names)


async def test_render_progress_pushes_interview_progress(store: InMemoryListingStore) -> None:
    server_instance, sink, _ = _build(store)
    result = await call_mcp_tool(
        server_instance,
        "render_progress",
        {"completed_slots": ["goal"], "open_slots": ["budget"]},
    )
    assert not result.isError
    assert len(sink.pushed) == 2  # createSurface + updateComponents, first call
    assert "createSurface" in sink.pushed[0]
    update = sink.pushed[1]["updateComponents"]
    root = next(c for c in update["components"] if c["id"] == "root")
    assert root["component"] == "InterviewProgress"
    assert root["phase"] == "interview"
    assert {"name": "goal", "status": "filled"} in root["slots"]
    assert {"name": "budget", "status": "open"} in root["slots"]


async def test_render_results_creates_one_car_card_per_item(store: InMemoryListingStore) -> None:
    server_instance, sink, _ = _build(store)
    args = {
        "weights": {"budget_fit": 1.0},
        "items": [
            {
                "source": "mock_autobazaar",
                "source_id": "AB-1",
                "rank": 1,
                "score": 0.9,
                "rationale": "cheapest of the shortlist",
            },
            {
                "source": "mock_autobazaar",
                "source_id": "AB-2",
                "rank": 2,
                "score": 0.8,
                "rationale": "second cheapest",
            },
        ],
    }
    result = await call_mcp_tool(server_instance, "render_results", args)
    assert not result.isError
    update = sink.pushed[-1]["updateComponents"]
    cards = [c for c in update["components"] if c["component"] == "CarCard"]
    assert len(cards) == 2
    root = next(c for c in update["components"] if c["id"] == "root")
    assert root["component"] == "Column"
    assert set(root["children"]) == {c["id"] for c in cards}


async def test_render_detail_fetches_the_real_listing(store: InMemoryListingStore) -> None:
    listing = store.listings[0]
    server_instance, sink, _ = _build(store)
    result = await call_mcp_tool(
        server_instance,
        "render_detail",
        {
            "source": listing.source,
            "source_id": listing.source_id,
            "show_powertrain_explainer": True,
        },
    )
    assert not result.isError
    update = sink.pushed[-1]["updateComponents"]
    explainer = next(
        (c for c in update["components"] if c["component"] == "PowertrainExplainer"), None
    )
    assert explainer is not None
    assert explainer["archetype"] == listing.powertrain_archetype.value
    assert explainer["modelSrc"] == f"/models/powertrain/{listing.powertrain_archetype.value}.glb"


async def test_render_detail_rejects_an_unknown_listing(store: InMemoryListingStore) -> None:
    server_instance, _, _ = _build(store)
    result = await call_mcp_tool(
        server_instance, "render_detail", {"source": "mock_autobazaar", "source_id": "NOPE"}
    )
    assert result.isError


async def test_render_tco_carries_the_break_even_month(store: InMemoryListingStore) -> None:
    server_instance, sink, _ = _build(store)
    args = {
        "horizon_months": 36,
        "items": [{"source": "mock_autobazaar", "source_id": "AB-1", "total_cost_eur": 21000.0}],
        "break_even_month": 5,
    }
    result = await call_mcp_tool(server_instance, "render_tco", args)
    assert not result.isError
    update = sink.pushed[-1]["updateComponents"]
    root = next(c for c in update["components"] if c["id"] == "root")
    assert root["component"] == "TcoChart"
    assert root["breakEvenMonth"] == 5


async def test_compose_surface_accepts_a_valid_tree(store: InMemoryListingStore) -> None:
    server_instance, sink, _ = _build(store)
    tree = {
        "components": [
            {"id": "root", "component": "Text", "text": "hello"},
        ]
    }
    result = await call_mcp_tool(server_instance, "compose_surface", {"tree": tree})
    assert not result.isError
    assert sink.pushed  # something was pushed


async def test_compose_surface_rejects_an_unknown_component(store: InMemoryListingStore) -> None:
    """CONSTITUTION II.4 / gate 6.3: the error reaches the model as a tool result, and
    nothing is forwarded to the renderer.
    """
    server_instance, sink, _ = _build(store)
    tree = {"components": [{"id": "root", "component": "TotallyMadeUp"}]}
    result = await call_mcp_tool(server_instance, "compose_surface", {"tree": tree})
    assert result.isError
    assert "UNKNOWN_COMPONENT" in result.content[0].text
    assert not sink.pushed


@pytest.mark.parametrize(
    "tree",
    [
        {  # dangling child reference
            "components": [{"id": "root", "component": "Card", "child": "missing"}]
        },
        {  # duplicate id
            "components": [
                {"id": "root", "component": "Text", "text": "a"},
                {"id": "root", "component": "Text", "text": "b"},
            ]
        },
    ],
)
async def test_compose_surface_rejects_structural_violations(
    store: InMemoryListingStore, tree: dict[str, object]
) -> None:
    server_instance, sink, _ = _build(store)
    result = await call_mcp_tool(server_instance, "compose_surface", {"tree": tree})
    assert result.isError
    assert not sink.pushed


async def test_compose_surface_rejects_a_tree_deeper_than_eight(
    store: InMemoryListingStore,
) -> None:
    # A chain of 9 nested Cards (root..n8) plus a Text leaf: depth 10 > MAX_TREE_DEPTH (8).
    chain_ids = ["root"] + [f"n{i}" for i in range(1, 9)] + ["leaf"]
    components: list[dict[str, object]] = [
        {"id": chain_ids[i], "component": "Card", "child": chain_ids[i + 1]}
        for i in range(len(chain_ids) - 1)
    ]
    components.append({"id": "leaf", "component": "Text", "text": "hi"})

    server_instance, sink, _ = _build(store)
    result = await call_mcp_tool(
        server_instance, "compose_surface", {"tree": {"components": components}}
    )
    assert result.isError
    assert "DEPTH_EXCEEDED" in result.content[0].text
    assert not sink.pushed


async def test_second_render_results_call_updates_not_recreates(
    store: InMemoryListingStore,
) -> None:
    """Gate 6.6: surface identity is stable across calls in the same session."""
    server_instance, sink, _ = _build(store)
    args = {
        "weights": {"budget_fit": 1.0},
        "items": [
            {
                "source": "mock_autobazaar",
                "source_id": "AB-1",
                "rank": 1,
                "score": 0.9,
                "rationale": "first pass",
            }
        ],
    }
    await call_mcp_tool(server_instance, "render_results", args)
    first_create_count = sum(1 for m in sink.pushed if "createSurface" in m)
    assert first_create_count == 1

    args["items"][0]["rationale"] = "re-ranked"
    await call_mcp_tool(server_instance, "render_results", args)
    second_create_count = sum(1 for m in sink.pushed if "createSurface" in m)
    assert second_create_count == 1, "a second render_results call created a new surface"
