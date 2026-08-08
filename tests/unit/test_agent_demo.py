"""`DEMO_MODE`'s full-flow runner (PHASE-3 §7), driven over the ten scripted personas that
back gate 3.1, 3.4, 3.5 and 3.8.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.adapters.store import InMemoryListingStore
from src.agent.demo import run_demo_session
from src.agent.phase_machine import Phase
from src.agent.research import traces_overlap

PERSONAS_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "personas.json"


def _personas() -> list[dict[str, object]]:
    return json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def demo_store() -> InMemoryListingStore:
    return InMemoryListingStore.seeded()


def test_ten_personas_fixture_exists_and_has_ten_entries() -> None:
    personas = _personas()
    assert len(personas) == 10
    assert len({p["name"] for p in personas}) == 10


@pytest.mark.parametrize("persona", _personas(), ids=lambda p: p["name"])
async def test_persona_reaches_a_complete_profile_within_the_interview_budget(
    persona: dict[str, object], demo_store: InMemoryListingStore
) -> None:
    """Gate 3.1: each of the ten personas fills every REQUIRED slot -- a genuinely complete
    profile, not a budget-forced hand-off with gaps -- inside the 12-turn INTERVIEW budget.
    """
    utterances: list[str] = persona["utterances"]  # type: ignore[assignment]
    result = await run_demo_session(
        utterances, store=demo_store, session_id=f"gate31-{persona['name']}"
    )
    assert len(utterances) <= 12
    assert result.state.profile.is_complete, (
        f"{persona['name']} left INTERVIEW without a complete profile: "
        f"{result.state.profile.missing_slots()}"
    )
    assert result.state.phase is not Phase.INTERVIEW


@pytest.mark.parametrize("persona", _personas(), ids=lambda p: p["name"])
async def test_persona_never_searches_before_two_slots_are_filled(
    persona: dict[str, object], demo_store: InMemoryListingStore
) -> None:
    """Gate 3.8, over the real interview -> research pipeline, not a synthetic profile."""
    result = await run_demo_session(
        list(persona["utterances"]),  # type: ignore[arg-type]
        store=demo_store,
        session_id=f"gate38-{persona['name']}",
    )
    assert result.search_denied_before_two_slots is False


async def test_researchers_run_with_genuinely_overlapping_timestamps(
    demo_store: InMemoryListingStore,
) -> None:
    """Gate 3.4: both marketplaces' research calls were actually concurrent."""
    persona = _personas()[0]
    result = await run_demo_session(
        list(persona["utterances"]), store=demo_store, session_id="gate34"
    )
    assert len(result.research_traces) >= 2
    assert traces_overlap(result.research_traces)


async def test_mid_recommend_constraint_change_returns_to_research(
    demo_store: InMemoryListingStore,
) -> None:
    """Gate 3.5: a stated change mid-RECOMMEND loops back through RESEARCH."""
    persona = next(p for p in _personas() if p.get("mid_recommend_utterance"))
    result = await run_demo_session(
        list(persona["utterances"]),  # type: ignore[arg-type]
        store=demo_store,
        session_id="gate35",
        mid_recommend_utterance=persona["mid_recommend_utterance"],  # type: ignore[arg-type]
    )
    research_visits = [i for i, p in enumerate(result.phase_history) if p is Phase.RESEARCH]
    assert len(research_visits) >= 2, (
        f"expected RESEARCH visited at least twice (initial + backward transition), "
        f"got history {result.phase_history}"
    )


async def test_demo_mode_completes_the_full_flow_with_no_api_key(
    monkeypatch: pytest.MonkeyPatch, demo_store: InMemoryListingStore
) -> None:
    """Gate 3.3, CONSTITUTION III.7: no ANTHROPIC_API_KEY, no DEMO_MODE env flag even needed
    for this module -- `demo.py` never constructs a `ClaudeSDKClient` at all.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    persona = _personas()[0]
    result = await run_demo_session(
        list(persona["utterances"]),
        store=demo_store,
        session_id="gate33",  # type: ignore[arg-type]
    )
    assert result.state.phase is Phase.TRANSACT
    assert result.state.booking_status == "draft_submitted"
