"""`for_audience` and `resolved_tool_names` (PHASE-2 §4).

The mechanism gate 2.6 depends on, tested in isolation from any real tool so a break here
points straight at `src/mcp/audience.py` rather than surfacing three servers downstream.
"""

from __future__ import annotations

from claude_agent_sdk import create_sdk_mcp_server, tool

from src.mcp.audience import (
    APP_ONLY,
    MODEL_AND_APP,
    MODEL_ONLY,
    ToolSpec,
    for_audience,
    resolved_tool_names,
)


@tool("visible_tool", "Visible to everyone. Call this when testing.", {"x": str})
async def _visible(args: dict[str, object]) -> dict[str, object]:
    return {"content": [{"type": "text", "text": "ok"}]}


@tool("hidden_tool", "Visible to the app only. Call this when testing.", {"x": str})
async def _hidden(args: dict[str, object]) -> dict[str, object]:
    return {"content": [{"type": "text", "text": "ok"}]}


SPECS = [
    ToolSpec(_visible, MODEL_AND_APP),
    ToolSpec(_hidden, APP_ONLY),
]


def test_for_audience_model_excludes_app_only_tools() -> None:
    tools = for_audience(SPECS, "model")
    assert [t.name for t in tools] == ["visible_tool"]


def test_for_audience_app_includes_everything() -> None:
    tools = for_audience(SPECS, "app")
    assert {t.name for t in tools} == {"visible_tool", "hidden_tool"}


def test_model_only_spec_is_absent_from_the_app_filter_too_if_not_marked() -> None:
    model_only_spec = ToolSpec(_visible, MODEL_ONLY)
    assert for_audience([model_only_spec], "app") == []


async def test_resolved_tool_names_matches_what_was_actually_registered() -> None:
    config = create_sdk_mcp_server("t", tools=for_audience(SPECS, "model"))
    assert await resolved_tool_names(config) == ("visible_tool",)
