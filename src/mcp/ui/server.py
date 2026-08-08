"""Builds `ui-mcp` as an `McpSdkServerConfig` (PHASE-2 §3). In-process only -- publishing a
server this tightly coupled to our own A2UI catalog would be meaningless (PHASE-2 §3).

All P6 dependencies (`session_id`, `sink`, `registry`, `store`, `phase`) are optional and
default to no-ops, so every existing caller (`orchestrator.py`, gate 2.6, `test_mcp_ui.py`'s
old signature) keeps working unchanged; a caller that wants real rendering wires them through.
"""

from __future__ import annotations

from collections.abc import Callable

from claude_agent_sdk import create_sdk_mcp_server
from claude_agent_sdk.types import McpSdkServerConfig

from src.adapters.store import ListingStore
from src.mcp.audience import Audience, for_audience
from src.mcp.ui.sink import UISink
from src.mcp.ui.surfaces import SurfaceRegistry
from src.mcp.ui.tools import build_tool_specs

SERVER_NAME = "ui-mcp"


def build_ui_server(
    *,
    audience: Audience = "model",
    session_id: str = "unbound",
    sink: UISink | None = None,
    registry: SurfaceRegistry | None = None,
    store: ListingStore | None = None,
    phase: Callable[[], str] | None = None,
) -> McpSdkServerConfig:
    specs = build_tool_specs(
        session_id=session_id, sink=sink, registry=registry, store=store, phase=phase
    )
    return create_sdk_mcp_server(SERVER_NAME, tools=for_audience(specs, audience))
