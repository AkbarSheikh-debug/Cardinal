"""Exit gate for PHASE 2 -- MCP.

    python scripts/gate_phase2.py

Criterion 2.1 talks to the standalone stdio server the way MCP Inspector would -- over the
real JSON-RPC wire protocol via `mcp.client.stdio` -- because Inspector itself is an
interactive browser tool with no CLI mode to script in CI; this is the scriptable
equivalent PHASE-2 §8's note about criterion 2.6 asks for elsewhere ("assert on the resolved
toolset ... not by reading config") applied to 2.1 too.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import anyio
from claude_agent_sdk import SdkMcpTool
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp import types as mcp_types
from scripts.gate_common import REPO_ROOT, Gate, Pending, python_executable
from src.adapters.store import InMemoryListingStore
from src.domain.marketplace import estimate_tokens
from src.mcp.audience import resolved_tool_names
from src.mcp.booking.server import build_booking_server
from src.mcp.booking.tools import build_tool_specs as booking_tool_specs
from src.mcp.marketplace.server import build_marketplace_server
from src.mcp.marketplace.tools import build_tool_specs as marketplace_tool_specs
from src.mcp.ui.tools import build_tool_specs as ui_tool_specs

MIN_DESCRIPTION_SENTENCES = 3
TRIGGER_PHRASE = "call this when"
MAX_SEARCH_RESULT_TOKENS = 4000
MAX_GET_LISTING_TOKENS = 800
APP_ONLY_BOOKING_TOOLS = {"submit_booking_draft", "confirm_booking"}


def _all_specs_including_hidden() -> list[SdkMcpTool[Any]]:
    """Every tool this phase defines, regardless of audience.

    Gates 2.2 and 2.3 hold `confirm_booking` to the same schema/description bar as anything
    the model sees -- being invisible to the model is not a licence to be sloppy, since P8's
    app code and MCP Inspector (pointed at an `audience="app"` build) both still read it.
    """
    store = InMemoryListingStore.seeded()
    specs = [*marketplace_tool_specs(store), *ui_tool_specs(), *booking_tool_specs()]
    return [spec.sdk_tool for spec in specs]


def _sentence_count(text: str) -> int:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    return len(sentences)


async def _call_tool(server_instance: Any, name: str, arguments: dict[str, Any]) -> Any:
    handler = server_instance.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    result = await handler(request)
    return result.root


def build_gate() -> Gate:
    gate = Gate(2, "MCP -- Tool protocol layer, three servers, registry manifest")

    store = InMemoryListingStore.seeded()
    marketplace_model = build_marketplace_server(store, audience="model")

    # -- 2.1 -------------------------------------------------------------------
    @gate.criterion(
        "2.1", "MCP Inspector connects to marketplace-mcp over stdio and lists all five tools"
    )
    def _() -> str:
        expected = {
            "search_cars",
            "get_listing",
            "check_availability",
            "get_quote",
            "compare_listings",
        }

        async def probe() -> list[str]:
            params = StdioServerParameters(
                command=python_executable(),
                args=["-m", "src.mcp.marketplace.stdio"],
                cwd=str(REPO_ROOT),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    return [t.name for t in listed.tools]

        names = anyio.run(probe)
        missing = expected - set(names)
        assert not missing, f"stdio server did not list {missing}; got {names}"
        return f"connected over stdio, tools/list -> {sorted(names)}"

    # -- 2.2 -------------------------------------------------------------------
    @gate.criterion(
        "2.2", 'every tool description >=3 sentences with an explicit "call this when" clause'
    )
    def _() -> str:
        tools = _all_specs_including_hidden()
        # 14 through P7 (marketplace 5 + ui 5 + booking 4); P8 added booking-mcp's
        # `mint_gesture_token` (CONSTITUTION I.2's third defence layer), making 15.
        assert len(tools) == 15, f"expected 15 tools across three servers, found {len(tools)}"
        short, missing_trigger = [], []
        for t in tools:
            if _sentence_count(t.description) < MIN_DESCRIPTION_SENTENCES:
                short.append(t.name)
            if TRIGGER_PHRASE not in t.description.lower():
                missing_trigger.append(t.name)
        assert not short, f"fewer than {MIN_DESCRIPTION_SENTENCES} sentences: {short}"
        assert not missing_trigger, f"missing a 'call this when' clause: {missing_trigger}"
        return f"{len(tools)}/{len(tools)} tools carry a >=3-sentence prescriptive description"

    # -- 2.3 -------------------------------------------------------------------
    @gate.criterion("2.3", "every input schema sets additionalProperties: false and strict: true")
    def _() -> str:
        tools = _all_specs_including_hidden()
        bad = []
        for t in tools:
            schema = t.input_schema
            if not isinstance(schema, dict) or schema.get("additionalProperties") is not False:
                bad.append(f"{t.name}: additionalProperties")
            if not isinstance(schema, dict) or schema.get("strict") is not True:
                bad.append(f"{t.name}: strict")
        assert not bad, f"schema discipline violated: {bad}"
        return f"{len(tools)}/{len(tools)} schemas set additionalProperties=false, strict=true"

    # -- 2.4 -------------------------------------------------------------------
    @gate.criterion("2.4", "search_cars result for the broadest query is <=20 items, <=4000 tokens")
    def _() -> str:
        async def run() -> Any:
            return await _call_tool(marketplace_model["instance"], "search_cars", {})

        result = anyio.run(run)
        assert not result.isError, f"search_cars errored: {result.content}"
        text = result.content[0].text
        import json

        page = json.loads(text)
        tokens = estimate_tokens(text)
        assert len(page["items"]) <= 20, f"{len(page['items'])} items in one page"
        assert tokens <= MAX_SEARCH_RESULT_TOKENS, f"{tokens} tokens"
        return (
            f"{len(page['items'])} items, total={page['total']}, "
            f"{tokens} tokens (cap {MAX_SEARCH_RESULT_TOKENS})"
        )

    # -- 2.5 -------------------------------------------------------------------
    @gate.criterion("2.5", "get_listing result is <=800 tokens")
    def _() -> str:
        async def run() -> tuple[Any, int]:
            search = await _call_tool(marketplace_model["instance"], "search_cars", {})
            import json

            first = json.loads(search.content[0].text)["items"][0]
            result = await _call_tool(
                marketplace_model["instance"],
                "get_listing",
                {"source": first["source"], "source_id": first["source_id"]},
            )
            return result, estimate_tokens(result.content[0].text)

        result, tokens = anyio.run(run)
        assert not result.isError, f"get_listing errored: {result.content}"
        assert tokens <= MAX_GET_LISTING_TOKENS, f"{tokens} tokens"
        return f"{tokens} tokens (cap {MAX_GET_LISTING_TOKENS})"

    # -- 2.6 -------------------------------------------------------------------
    @gate.criterion("2.6", "confirm_booking is absent from the tool list presented to the model")
    def _() -> str:
        async def run() -> tuple[tuple[str, ...], tuple[str, ...]]:
            model_names = await resolved_tool_names(build_booking_server(audience="model"))
            app_names = await resolved_tool_names(build_booking_server(audience="app"))
            return model_names, app_names

        model_names, app_names = anyio.run(run)
        leaked = APP_ONLY_BOOKING_TOOLS & set(model_names)
        assert not leaked, f"app-only tools visible to the model: {leaked}"
        missing_from_app = APP_ONLY_BOOKING_TOOLS - set(app_names)
        assert not missing_from_app, (
            f"{missing_from_app} missing even from the app-facing build -- "
            "that would mean they were never implemented, not deliberately hidden"
        )
        return (
            f"model-facing booking-mcp resolves to {model_names} (no confirm_booking, "
            f"no submit_booking_draft)\n"
            f"app-facing booking-mcp resolves to {app_names} (both present) -- "
            "resolved via the SDK's own Server.request_handlers, not read from config"
        )

    # -- 2.7 -------------------------------------------------------------------
    @gate.criterion(
        "2.7", "in-process and stdio builds of marketplace-mcp return byte-identical results"
    )
    def _() -> str:
        args = {"categories": ["suv"], "sort": "price_asc", "page_size": 5}

        async def in_process() -> str:
            result = await _call_tool(marketplace_model["instance"], "search_cars", args)
            return str(result.content[0].text)

        async def over_stdio() -> str:
            params = StdioServerParameters(
                command=python_executable(),
                args=["-m", "src.mcp.marketplace.stdio"],
                cwd=str(REPO_ROOT),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("search_cars", args)
                    text_block = result.content[0]
                    assert isinstance(text_block, mcp_types.TextContent)
                    return text_block.text

        in_proc_text = anyio.run(in_process)
        stdio_text = anyio.run(over_stdio)
        assert in_proc_text == stdio_text, "in-process and stdio results diverged"
        return f"identical {len(in_proc_text)}-byte result for {args} across both transports"

    # -- 2.8 -------------------------------------------------------------------
    @gate.criterion("2.8", "[SCALE] registry manifest validates against the registry schema")
    def _() -> str:
        raise Pending("not built -- marketplace-mcp registry submission is [SCALE] (PHASE-2 §7)")

    return gate


def main() -> int:
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
