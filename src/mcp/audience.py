"""Tool visibility: the enforcement mechanism behind CONSTITUTION I.2 (PHASE-2 §4).

A tool's `audience` says who is allowed to see it exists. `"model"` means the SDK hands it
to Claude as a callable tool; `"app"` means only our own backend code invokes its handler
directly. `confirm_booking` carries `audience=("app",)` -- not a permission check that runs
*after* the model asks, but the tool never being placed in front of it in the first place.

`resolved_tool_names` is what makes gate 2.6 mean something: it does not read this module's
`audience` field back to itself, it calls into the *real* MCP `Server` object's own
registered `list_tools` handler -- the same code path `create_sdk_mcp_server` wires up and
the same one the CLI calls during capability negotiation -- and reports whatever comes back.

`for_audience` is also the one place every tool, on every server, passes through before it's
handed to `create_sdk_mcp_server` -- which makes it the single choke point PHASE-9 §3/gate 9.2
needs for "every MCP tool call appears as a span with args hash and duration": each handler is
wrapped in a `tool.<name>` span here, using OpenTelemetry's own API directly rather than
importing `src/agent/tracing.py` -- `src/mcp` never imports `src/agent` (PLAN-00 §2's one-way
layering), and the API/SDK split means this works against whatever `TracerProvider` the
process configured (a real one in `src/api/main.py`'s lifespan, a harmless no-op in a test
that never calls `configure_tracing`) without this module needing to know which.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from claude_agent_sdk import SdkMcpTool
from claude_agent_sdk.types import McpSdkServerConfig
from opentelemetry import trace

from mcp import types as mcp_types

_TRACER = trace.get_tracer("cardinal.mcp")

Audience = Literal["model", "app"]

MODEL_AND_APP: tuple[Audience, ...] = ("model", "app")
MODEL_ONLY: tuple[Audience, ...] = ("model",)
APP_ONLY: tuple[Audience, ...] = ("app",)


@dataclass(frozen=True)
class ToolSpec:
    """One tool, plus who is allowed to see it."""

    sdk_tool: SdkMcpTool[Any]
    audience: tuple[Audience, ...]

    @property
    def name(self) -> str:
        return self.sdk_tool.name


def _hash_tool_args(args: Any) -> str:
    canonical = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _traced_handler(
    name: str, handler: Callable[[Any], Awaitable[dict[str, Any]]]
) -> Callable[[Any], Awaitable[dict[str, Any]]]:
    async def _wrapped(args: Any) -> dict[str, Any]:
        with _TRACER.start_as_current_span(f"tool.{name}") as span:
            span.set_attribute("tool.name", name)
            span.set_attribute("tool.args_hash", _hash_tool_args(args))
            return await handler(args)

    return _wrapped


def for_audience(specs: Sequence[ToolSpec], audience: Audience) -> list[SdkMcpTool[Any]]:
    """The tools a given audience is allowed to see -- filtered *before* the SDK server is
    built, so an excluded tool is never registered rather than merely disallowed. Every
    surviving tool's handler is wrapped in a tracing span (gate 9.2); the wrapper is
    transparent -- same input, same output, same exceptions -- so gate 2.7's byte-identical
    in-process-vs-stdio comparison is unaffected by it.
    """
    return [
        replace(spec.sdk_tool, handler=_traced_handler(spec.sdk_tool.name, spec.sdk_tool.handler))
        for spec in specs
        if audience in spec.audience
    ]


async def resolved_tools(config: McpSdkServerConfig) -> tuple[mcp_types.Tool, ...]:
    """The full `Tool` objects the SDK's own `Server` reports for `tools/list`.

    Calls the real handler `create_sdk_mcp_server` registered via `@server.list_tools()`
    (`mcp.server.lowlevel.Server` calls it the same way internally to refresh its tool
    cache -- see `_get_cached_tool_definition`). Nothing here is our own bookkeeping.
    """
    server = config["instance"]
    handler = server.request_handlers.get(mcp_types.ListToolsRequest)
    if handler is None:
        # The SDK only registers a list_tools handler when `tools=[...]` is non-empty
        # (confirmed against claude_agent_sdk.create_sdk_mcp_server directly). A server
        # with zero tools for this audience -- e.g. ui-mcp's "app" build, which has no
        # app-only tools today -- is a legitimate empty set, not a missing handler.
        return ()
    result = await handler(None)
    assert isinstance(result.root, mcp_types.ListToolsResult)
    return tuple(result.root.tools)


async def resolved_tool_names(config: McpSdkServerConfig) -> tuple[str, ...]:
    return tuple(t.name for t in await resolved_tools(config))
