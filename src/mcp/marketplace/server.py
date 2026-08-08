"""Builds `marketplace-mcp` as an `McpSdkServerConfig` (PHASE-2 §3).

The same `Server` instance backs both transports: `build_marketplace_server` is called once
by the in-process agent integration and once by `src.mcp.marketplace.stdio`, and gate 2.7
diffs their output for a fixed query. There is only one implementation to drift.
"""

from __future__ import annotations

from claude_agent_sdk import create_sdk_mcp_server
from claude_agent_sdk.types import McpSdkServerConfig

from src.adapters.store import ListingStore
from src.mcp.audience import Audience, for_audience
from src.mcp.marketplace.tools import build_tool_specs

SERVER_NAME = "marketplace-mcp"


def build_marketplace_server(
    store: ListingStore, *, audience: Audience = "model"
) -> McpSdkServerConfig:
    specs = build_tool_specs(store)
    return create_sdk_mcp_server(SERVER_NAME, tools=for_audience(specs, audience))
