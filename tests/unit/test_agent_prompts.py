"""CONSTITUTION III.6 / gate 3.7: prompts live in files, and every prompt the roster uses
actually loads.
"""

from __future__ import annotations

import pytest

from src.agent.prompts import load_prompt
from src.agent.subagents import build_roster

PROMPT_NAMES = (
    "orchestrator_system",
    "interviewer",
    "researcher",
    "critic",
    "explainer",
    "slot_extraction",
)


@pytest.mark.parametrize("name", PROMPT_NAMES)
def test_every_prompt_file_loads_and_is_non_empty(name: str) -> None:
    text = load_prompt(name)
    assert text.strip()


def test_missing_prompt_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")


def test_load_prompt_is_cached() -> None:
    assert load_prompt("interviewer") is load_prompt("interviewer")


def test_roster_prompts_match_the_files_on_disk() -> None:
    roster = build_roster()
    assert roster["interviewer"].prompt == load_prompt("interviewer")
    assert roster["researcher"].prompt == load_prompt("researcher")
    assert roster["critic"].prompt == load_prompt("critic")
    assert roster["explainer"].prompt == load_prompt("explainer")


def test_interviewer_has_no_tools() -> None:
    """PHASE-3 §4: the interviewer is explicitly told not to search."""
    roster = build_roster()
    assert roster["interviewer"].tools == []


def test_researcher_and_critic_and_explainer_all_carry_market_tools() -> None:
    roster = build_roster()
    for name in ("researcher", "critic", "explainer"):
        tools = roster[name].tools or []
        assert any(t.startswith("mcp__market__") for t in tools)
