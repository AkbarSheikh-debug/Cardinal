"""Exit gate for PHASE 3 -- AGENT.

    python scripts/gate_phase3.py                  # 3.2 is PENDING with no Postgres running
    python scripts/gate_phase3.py --require-stack   # 3.2 must genuinely pass

Every criterion below runs deterministically with no `ANTHROPIC_API_KEY` and no live
`ClaudeSDKClient` session -- `src/agent/demo.py`'s `run_demo_session` is what the ten
personas actually drive, and it never shells out to the `claude` CLI (DECISIONS.md D-012's
reasoning: a check that needs a subprocess and live credentials cannot run deterministically
in CI, so the gate verifies every piece `orchestrator.py` is built from independently
instead of the live session itself).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

import anyio

from scripts.gate_common import REPO_ROOT, Gate, Pending
from src.adapters.db.session import ENV_DATABASE_URL
from src.adapters.store import InMemoryListingStore
from src.agent.demo import run_demo_session
from src.agent.phase_machine import Phase, new_session
from src.agent.research import traces_overlap

MAX_PROMPT_CHARS = 200
PERSONAS_PATH = REPO_ROOT / "tests" / "fixtures" / "demo" / "personas.json"


def _load_personas() -> list[dict[str, object]]:
    return json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))


def build_gate(*, require_stack: bool) -> Gate:
    gate = Gate(3, "AGENT -- Orchestration, phase machine, subagents, demo mode")

    store = InMemoryListingStore.seeded()
    personas = _load_personas()

    # -- 3.1 -------------------------------------------------------------------
    @gate.criterion(
        "3.1", "10 scripted personas each reach a complete RequirementProfile within budget"
    )
    def _() -> str:
        assert len(personas) == 10, f"expected 10 personas, found {len(personas)}"

        async def run_all() -> list[tuple[str, bool, int]]:
            outcomes = []
            for persona in personas:
                utterances = list(persona["utterances"])
                result = await run_demo_session(
                    utterances, store=store, session_id=f"gate31-{uuid.uuid4()}"
                )
                outcomes.append(
                    (persona["name"], result.state.profile.is_complete, len(utterances))
                )
            return outcomes

        outcomes = anyio.run(run_all)
        incomplete = [name for name, complete, _ in outcomes if not complete]
        assert not incomplete, f"never completed a profile: {incomplete}"
        lines = [f"{name}: complete in {n} turn(s)" for name, _, n in outcomes]
        return "\n".join(lines)

    # -- 3.2 -------------------------------------------------------------------
    @gate.criterion(
        "3.2", "a session survives process restart: resume by session_id recovers state exactly"
    )
    def _() -> str:
        database_url = os.environ.get(ENV_DATABASE_URL)
        if not database_url:
            if require_stack:
                raise AssertionError(f"{ENV_DATABASE_URL} unset and --require-stack passed")
            raise Pending(
                f"{ENV_DATABASE_URL} unset -- start Postgres (`docker compose up -d postgres`), "
                "then re-run with --require-stack"
            )

        from datetime import date

        from src.adapters.db.session import run_async, session_factory
        from src.agent.session_store import PostgresSessionStateStore
        from src.domain.enums import OfferType, VehicleCategory
        from src.domain.money import Money

        async def round_trip() -> bool:
            store_ = PostgresSessionStateStore(session_factory())
            state = new_session(str(uuid.uuid4()))
            profile = state.profile
            profile.goal = profile.goal.fill(OfferType.BUY, confidence=0.9, turn=1, locked=True)
            profile.category = profile.category.fill([VehicleCategory.SUV], confidence=0.8, turn=2)
            profile.budget = profile.budget.fill(
                Money.of("27500.50"), confidence=0.95, turn=3, locked=True
            )
            profile.target_date = profile.target_date.fill(
                date(2026, 10, 1), confidence=0.7, turn=3
            )
            state = state.model_copy(
                update={"phase": Phase.RESEARCH, "turn_in_phase": 2, "profile": profile}
            )
            await store_.save(state, user_id="gate32")

            # A fresh store object over a fresh sessionmaker -- the closest an in-process
            # gate can get to "a different process restarted and resumed."
            resumed = await PostgresSessionStateStore(session_factory()).load(state.session_id)
            return resumed == state

        ok = run_async(round_trip())
        assert ok, "resumed state did not equal the saved state"
        return "save -> load through a fresh store instance recovered phase + profile exactly"

    # -- 3.3 -------------------------------------------------------------------
    @gate.criterion("3.3", "DEMO_MODE=true completes the full flow with ANTHROPIC_API_KEY unset")
    def _() -> str:
        had_key = "ANTHROPIC_API_KEY" in os.environ
        saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:

            async def run() -> object:
                persona = personas[0]
                return await run_demo_session(
                    list(persona["utterances"]), store=store, session_id=f"gate33-{uuid.uuid4()}"
                )

            result = anyio.run(run)
        finally:
            if had_key and saved_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved_key

        assert result.state.phase is Phase.TRANSACT, f"stalled in {result.state.phase}"
        assert result.state.booking_status == "draft_submitted", "never reached a booking draft"
        return (
            f"persona {personas[0]['name']!r} reached {result.state.phase.value} "
            f"(booking_status={result.state.booking_status!r}) with no ANTHROPIC_API_KEY set"
        )

    # -- 3.4 -------------------------------------------------------------------
    @gate.criterion(
        "3.4", "both researcher subagents appear in the trace with overlapping timestamps"
    )
    def _() -> str:
        async def run() -> object:
            persona = personas[0]
            return await run_demo_session(
                list(persona["utterances"]), store=store, session_id=f"gate34-{uuid.uuid4()}"
            )

        result = anyio.run(run)
        traces = result.research_traces
        assert len(traces) >= 2, f"only {len(traces)} researcher trace(s)"
        assert traces_overlap(traces), f"no overlap between traces: {traces}"
        spans = ", ".join(f"{t.source}=[{t.started_at:.4f}, {t.finished_at:.4f}]" for t in traces)
        return f"{len(traces)} researchers, overlapping spans: {spans}"

    # -- 3.5 -------------------------------------------------------------------
    @gate.criterion("3.5", "a backward transition mid-RECOMMEND returns to RESEARCH and re-ranks")
    def _() -> str:
        persona = next(p for p in personas if p.get("mid_recommend_utterance"))

        async def run() -> object:
            return await run_demo_session(
                list(persona["utterances"]),
                store=store,
                session_id=f"gate35-{uuid.uuid4()}",
                mid_recommend_utterance=persona["mid_recommend_utterance"],
            )

        result = anyio.run(run)
        research_visits = sum(1 for p in result.phase_history if p is Phase.RESEARCH)
        assert research_visits >= 2, f"RESEARCH visited {research_visits}x: {result.phase_history}"
        return (
            f"{persona['name']!r} + {persona['mid_recommend_utterance']!r} mid-RECOMMEND -> "
            f"RESEARCH visited {research_visits}x; final phase {result.state.phase.value}"
        )

    # -- 3.6 -------------------------------------------------------------------
    @gate.criterion(
        "3.6", "every tool call appears in the PreToolUse audit log with session, turn, args hash"
    )
    def _() -> str:
        async def run() -> object:
            persona = personas[0]
            return await run_demo_session(
                list(persona["utterances"]), store=store, session_id=f"gate36-{uuid.uuid4()}"
            )

        result = anyio.run(run)
        entries = result.audit_log.for_session(result.state.session_id)
        assert entries, "no audit entries recorded"
        for entry in entries:
            assert entry.session_id == result.state.session_id
            assert isinstance(entry.turn, int)
            assert re.fullmatch(r"[0-9a-f]{64}", entry.args_hash), (
                f"bad args hash: {entry.args_hash}"
            )
            assert entry.ts
        return f"{len(entries)} tool calls audited, each with session id, turn, sha256 args hash"

    # -- 3.7 -------------------------------------------------------------------
    @gate.criterion(
        "3.7", "prompts/ is the only source of prompt text -- no src/ literal exceeds 200 chars"
    )
    def _() -> str:
        prompts_dir = REPO_ROOT / "prompts"
        assert prompts_dir.is_dir(), "prompts/ does not exist"
        prompt_files = sorted(p.name for p in prompts_dir.glob("*.md"))
        assert prompt_files, "prompts/ has no .md files"

        offenders: list[str] = []
        for path in (REPO_ROOT / "src").rglob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if len(stripped) > MAX_PROMPT_CHARS and stripped.startswith(('"', "'", 'f"')):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
        assert not offenders, f"prompt strings over {MAX_PROMPT_CHARS} chars: {offenders}"
        names = ", ".join(prompt_files)
        return f"{len(prompt_files)} prompt files: {names}; no long literal in src/"

    # -- 3.8 -------------------------------------------------------------------
    @gate.criterion(
        "3.8", "interview never emits a search before >=2 slots are filled (over the 10 personas)"
    )
    def _() -> str:
        async def run_all() -> list[tuple[str, bool]]:
            outcomes = []
            for persona in personas:
                result = await run_demo_session(
                    list(persona["utterances"]), store=store, session_id=f"gate38-{uuid.uuid4()}"
                )
                outcomes.append((persona["name"], result.search_denied_before_two_slots))
            return outcomes

        outcomes = anyio.run(run_all)
        violated = [name for name, denied in outcomes if denied]
        assert not violated, (
            f"search_gate had to deny a search for: {violated} -- the interview let a "
            "search through with fewer than 2 filled slots"
        )
        return (
            f"{len(outcomes)}/{len(outcomes)} personas: search_gate never had to deny a "
            "search_cars call (see tests/unit/test_agent_guardrails.py for the gate denying "
            "an under-filled profile directly)"
        )

    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-stack",
        action="store_true",
        help="fail criterion 3.2 instead of reporting it PENDING when no database is configured",
    )
    args = parser.parse_args(argv)
    return build_gate(require_stack=args.require_stack).run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
