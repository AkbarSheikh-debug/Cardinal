"""Exit gate for PHASE 4 -- MEMORY.

    python scripts/gate_phase4.py                  # 4.1 is PENDING with no Postgres running
    python scripts/gate_phase4.py --require-stack   # 4.1 must genuinely pass

`[MVP]` criteria (4.1-4.3) run today. `[SCALE]` criteria (4.4-4.8 -- episodic recall,
contradiction handling, progressive disclosure, drift detection, forget_me) are explicitly
deferred (PHASE-4 §2 "Out" analogue -- CONSTITUTION III.3, MVP before SCALE always) and each
reports PENDING with a named reason rather than being silently absent, the same convention
gate 2.8 established for the MCP registry manifest.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

import anyio

from scripts.gate_common import REPO_ROOT, Gate, Pending
from src.adapters.db.session import ENV_DATABASE_URL
from src.adapters.store import InMemoryListingStore
from src.agent.demo import run_demo_session
from src.agent.extraction import apply_updates
from src.agent.journal import DecisionJournal, explain, session_uuid
from src.domain.memory import DecisionKind
from src.domain.profile import RequirementProfile

PERSONAS_PATH = REPO_ROOT / "tests" / "fixtures" / "demo" / "personas.json"


def build_gate(*, require_stack: bool) -> Gate:
    gate = Gate(4, "MEMORY -- Four tiers, consolidation, drift, forget-me")

    # -- 4.1 [MVP] ---------------------------------------------------------------
    @gate.criterion(
        "4.1", "profile survives process restart; every slot's confidence/source_turn intact"
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

        from src.adapters.db.session import run_async, session_factory
        from src.agent.phase_machine import Phase, new_session
        from src.agent.session_store import PostgresSessionStateStore
        from src.domain.enums import OfferType, VehicleCategory
        from src.domain.money import Money

        async def round_trip() -> tuple[bool, bool]:
            store = PostgresSessionStateStore(session_factory())
            state = new_session(str(uuid.uuid4()))
            profile = state.profile
            profile.goal = profile.goal.fill(OfferType.BUY, confidence=0.91, turn=1, locked=True)
            profile.category = profile.category.fill(
                [VehicleCategory.WAGON], confidence=0.77, turn=2
            )
            profile.budget = profile.budget.fill(
                Money.of("31250.00"), confidence=0.88, turn=4, locked=True
            )
            state = state.model_copy(
                update={"phase": Phase.RESEARCH, "turn_in_phase": 1, "profile": profile}
            )
            await store.save(state, user_id="gate41")

            # A fresh store instance over a fresh sessionmaker stands in for a restarted
            # process, same as gate 3.2 -- the working-state tier this criterion checks is
            # the exact mechanism P3 already built (PHASE-4 §3.1 overlaps PHASE-3 §8 gate 3.2
            # on purpose: "code-owned working state" is one mechanism, checked from two angles).
            resumed = await PostgresSessionStateStore(session_factory()).load(state.session_id)
            assert resumed is not None
            slots_intact = (
                resumed.profile.goal.confidence == 0.91
                and resumed.profile.goal.source_turn == 1
                and resumed.profile.category.confidence == 0.77
                and resumed.profile.category.source_turn == 2
                and resumed.profile.budget.confidence == 0.88
                and resumed.profile.budget.source_turn == 4
            )
            return slots_intact, resumed == state

        slots_intact, exact = run_async(round_trip())
        assert slots_intact, "confidence/source_turn did not survive the round trip"
        assert exact, "resumed profile was not byte-identical to the saved one"
        return (
            "save -> load through a fresh store instance kept every slot's "
            "confidence and source_turn"
        )

    # -- 4.2 [MVP] ---------------------------------------------------------------
    @gate.criterion("4.2", "a locked slot is not modified by a later low-confidence inference")
    def _() -> str:
        from src.agent.extraction import SlotUpdate
        from src.domain.enums import VehicleCategory
        from src.domain.money import Money

        profile = RequirementProfile()
        locked = apply_updates(
            profile,
            (SlotUpdate("budget", Money.of("28000"), 0.95, True),),
            turn=1,
        )
        assert locked.budget.locked, "the stated budget did not lock"

        drifted = apply_updates(
            locked,
            (
                SlotUpdate("budget", Money.of("45000"), 0.4, False),
                SlotUpdate("category", [VehicleCategory.LUXURY], 0.4, False),
            ),
            turn=9,
        )
        assert drifted.budget.value == Money.of("28000"), (
            f"locked budget drifted to {drifted.budget.value} from a confidence-0.4 inference"
        )
        assert drifted.budget.locked, "budget lost its locked flag"
        assert drifted.budget.source_turn == 1, "locked slot's source_turn moved"
        # A low-confidence inference on an *unlocked* slot still applies -- the guard is
        # specific to `locked`, not a blanket freeze on every slot once one is locked.
        assert drifted.category.value == [VehicleCategory.LUXURY], (
            "an unlocked slot was wrongly frozen alongside the locked one"
        )
        return (
            "turn-1 locked budget (EUR 28000) survived a turn-9 confidence-0.4 inference of "
            "EUR 45000 unchanged; the unlocked category slot in the same turn did update"
        )

    # -- 4.3 [MVP] ---------------------------------------------------------------
    @gate.criterion(
        "4.3", "journal answers 'why rank A over B' from a recorded row, zero model calls"
    )
    def _() -> str:
        import json

        personas = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))
        persona = personas[0]
        store = InMemoryListingStore.seeded()
        session_id = f"gate43-{uuid.uuid4()}"

        had_key = "ANTHROPIC_API_KEY" in os.environ
        saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:

            async def run() -> tuple[object, DecisionJournal, str]:
                result = await run_demo_session(
                    list(persona["utterances"]), store=store, session_id=session_id
                )
                recorded = await result.journal.latest_by_kind(
                    session_uuid(result.state.session_id), DecisionKind.RECOMMENDATION_MADE
                )
                assert recorded is not None, "RECOMMEND never wrote a DecisionEntry"
                # A *second*, independent lookup -- this is `explain()`'s only code path, and
                # it never imports an SDK client or touches the network (`src/agent/journal.py`
                # has no such import), so "zero model calls" holds by construction, not mocking.
                answer = await explain(
                    result.journal,
                    session_uuid(result.state.session_id),
                    kind=DecisionKind.RECOMMENDATION_MADE,
                )
                assert answer is not None
                return result, result.journal, answer

            result, journal, answer = anyio.run(run)
        finally:
            if had_key and saved_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved_key

        original = anyio.run(
            lambda: journal.latest_by_kind(
                session_uuid(result.state.session_id), DecisionKind.RECOMMENDATION_MADE
            )
        )
        assert original is not None
        assert answer == original.rationale, (
            "explain() did not return the stored rationale verbatim"
        )
        selected = result.state.selected_candidate
        assert selected is not None, "persona never reached a recommendation"
        return (
            f"explain() returned the recorded rationale for {selected!r} byte-identical to "
            f"the row `_record_recommendation` wrote, with ANTHROPIC_API_KEY unset "
            f"({len(answer)} chars, inputs_hash={original.inputs_hash[:12]}...)"
        )

    # -- 4.4 [SCALE] ---------------------------------------------------------------
    @gate.criterion(
        "4.4", "[SCALE] second session for a known user recalls >=1 prior constraint unprompted"
    )
    def _() -> str:
        raise Pending(
            "episodic memory (remember/recall tool, MEMORY.md index) not built -- [SCALE]"
        )

    # -- 4.5 [SCALE] ---------------------------------------------------------------
    @gate.criterion(
        "4.5", "[SCALE] contradicting memory sets superseded_by; recall returns the newer"
    )
    def _() -> str:
        raise Pending("contradiction handling over MemoryRecord.superseded_by not built -- [SCALE]")

    # -- 4.6 [SCALE] ---------------------------------------------------------------
    @gate.criterion("4.6", "[SCALE] memory index for 50 memories is <=800 tokens")
    def _() -> str:
        raise Pending("MEMORY.md-style progressive-disclosure index not built -- [SCALE]")

    # -- 4.7 [SCALE] ---------------------------------------------------------------
    @gate.criterion("4.7", "[SCALE] drift detector fires on a scripted divergence, asks a question")
    def _() -> str:
        raise Pending("preference-drift detector over the interaction log not built -- [SCALE]")

    # -- 4.8 [SCALE] ---------------------------------------------------------------
    @gate.criterion("4.8", "[SCALE] forget_me leaves zero rows across all four stores + Langfuse")
    def _() -> str:
        raise Pending("forget_me erasure path not built -- [SCALE]; Langfuse itself is P9's")

    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-stack",
        action="store_true",
        help="fail criterion 4.1 instead of reporting it PENDING when no database is configured",
    )
    args = parser.parse_args(argv)
    return build_gate(require_stack=args.require_stack).run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
