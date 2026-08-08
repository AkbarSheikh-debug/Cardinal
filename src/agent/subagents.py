"""The subagent roster (PHASE-3 §4).

`researcher` is defined once and launched twice -- once per registered marketplace source --
in the same orchestrator turn, per `registered_source_names()` (`src/adapters/registry.py`);
that is what makes the fan-out `Sequence[str]`-driven rather than a hardcoded "x2" that
silently stops covering a third marketplace later. Tool names are namespaced the way the
Claude Agent SDK exposes MCP tools to the model: `mcp__<server-key>__<tool-name>`, where the
server keys (`market`, `ui`, `booking`) match `orchestrator.py`'s `mcp_servers` mapping.

Keep these short and single-purpose (PHASE-3 §4: "the reference shape is Claude Code's own
Explore agent at ~870 tokens") -- the prompt files in `prompts/` are the *content*; this
module only wires model, effort and tool scope per role.
"""

from __future__ import annotations

import os

from claude_agent_sdk import AgentDefinition

from src.agent.prompts import load_prompt

#: PLAN-00 §6.7 / PHASE-3 §5 specifies `claude-opus-5` for the orchestrator tier: long-horizon
#: multistep work, 1M context. That is the right routing for a funded deployment and the wrong
#: one for development against a metered key -- measured live, one INTERVIEW turn on
#: opus-5/`effort=high`/adaptive thinking took ~72s and two serialised Opus calls (orchestrator
#: plus the `interviewer` subagent it delegates to). `CARDINAL_AGENT_MODEL` selects the routing
#: without editing code; the default is the cheap, fast one so nobody burns a budget by
#: forgetting to set it. Set `CARDINAL_AGENT_MODEL=claude-opus-5` for the plan's routing.
ORCHESTRATOR_MODEL = os.environ.get("CARDINAL_AGENT_MODEL", "claude-haiku-4-5").strip()

_MARKET = "mcp__market__"


def build_roster() -> dict[str, AgentDefinition]:
    return {
        "interviewer": AgentDefinition(
            description=(
                "Elicits the user's goal, vehicle category, budget and target date through "
                "conversation alone, with no search tool -- runs the INTERVIEW phase."
            ),
            prompt=load_prompt("interviewer"),
            tools=[],
            model=ORCHESTRATOR_MODEL,
            effort="medium",
        ),
        "researcher": AgentDefinition(
            description=(
                "Searches one marketplace for candidates matching the RequirementProfile and "
                "returns candidate ids with a one-line note each, never full records. Launch "
                "one instance per registered marketplace, in the same turn, for genuine "
                "concurrency (PHASE-3 §4)."
            ),
            prompt=load_prompt("researcher"),
            tools=[
                f"{_MARKET}search_cars",
                f"{_MARKET}get_listing",
                f"{_MARKET}check_availability",
            ],
            model=ORCHESTRATOR_MODEL,
            effort="low",
        ),
        "critic": AgentDefinition(
            description=(
                "Reviews the top candidates against every hard filter and the stated budget "
                "before anything reaches the user in RECOMMEND."
            ),
            prompt=load_prompt("critic"),
            tools=[f"{_MARKET}get_listing"],
            model=ORCHESTRATOR_MODEL,
            effort="high",
        ),
        "explainer": AgentDefinition(
            description=(
                "Turns a deterministic ScoreBreakdown into grounded prose, with a citable "
                "listing field behind every number it states."
            ),
            prompt=load_prompt("explainer"),
            tools=[f"{_MARKET}get_listing"],
            model=ORCHESTRATOR_MODEL,
            effort="medium",
        ),
    }
