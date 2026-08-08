"""`DEMO_MODE` (PHASE-3 §7, CONSTITUTION III.7): the complete flow -- interview, research,
recommend, transact -- with no `ANTHROPIC_API_KEY` and no live `ClaudeSDKClient` session.

`DemoSlotExtractor` stands in for the live haiku extraction call and `dispatch_researchers`
runs against the real seeded catalogue in place of the two live `researcher` subagents.
Everything else -- the phase machine, the audit hook, the search-gate guardrail -- is the
exact same code `orchestrator.py`'s live path runs; this module only swaps the two things
that would otherwise need a model.

RECOMMEND and TRANSACT are P3's minimum viable pass-through, not P5/P8's real logic (PHASE-3
§2 "Out": scoring is P5's, commerce is P8's). The demo picks the first surviving candidate
and opens a booking draft so the flow has somewhere to end -- a real ranking and a real
payment gateway are later phases' jobs.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from claude_agent_sdk import ToolPermissionContext
from opentelemetry import trace

from src.adapters.store import InMemoryListingStore, ListingStore
from src.agent.extraction import DemoSlotExtractor, SlotExtractor
from src.agent.guardrails import AuditLog, StateLookup, build_audit_hook, build_search_gate
from src.agent.interview import process_turn
from src.agent.journal import (
    DecisionJournal,
    InMemoryDecisionJournal,
    compute_inputs_hash,
    session_uuid,
)
from src.agent.phase_machine import Phase, SessionState, advance, begin_turn, new_session
from src.agent.research import ResearchTrace, dispatch_researchers
from src.agent.tracing import (
    configure_tracing,
    get_tracer,
    phase_span,
    scoring_span,
    tool_call_span,
)
from src.domain.listing import Listing
from src.domain.memory import DecisionEntry, DecisionKind
from src.domain.ranking import RankingResult, critic_pass, rank
from src.domain.scoring import RankedResult

#: Deliberately small but nonzero -- see `research.py` for why zero latency makes the
#: overlap gate 3.4 checks for unstable against an in-memory store.
RESEARCH_SIMULATED_LATENCY_S = 0.02

RecordTurn = Callable[[str, dict[str, object]], Awaitable[None]]


@dataclass
class DemoRunResult:
    state: SessionState
    phase_history: list[Phase] = field(default_factory=list)
    research_traces: tuple[ResearchTrace, ...] = ()
    audit_log: AuditLog = field(default_factory=AuditLog)
    journal: DecisionJournal = field(default_factory=InMemoryDecisionJournal)
    search_denied_before_two_slots: bool = False
    #: P5's real ranking pass and its post-critic survivors (PHASE-5 SS3, SS8) -- exposed here
    #: (not just folded into the journal) so gates 5.1/5.4/5.8 and callers can inspect the
    #: full breakdown, not only which single candidate got selected.
    ranking_result: RankingResult | None = None
    critic_survivors: tuple[RankedResult, ...] = ()
    critic_violations: tuple[str, ...] = ()


async def run_demo_session(
    utterances: list[str],
    *,
    store: ListingStore | None = None,
    extractor: SlotExtractor | None = None,
    session_id: str | None = None,
    mid_recommend_utterance: str | None = None,
    journal: DecisionJournal | None = None,
    decline_at_checkout: bool = False,
) -> DemoRunResult:
    """Drive one persona's scripted utterances through all four phases.

    `mid_recommend_utterance`, if given, is applied once RECOMMEND is reached and before a
    candidate is picked -- this is what exercises the backward transition (PHASE-3 §3, gate
    3.5) when it changes a required slot. `decline_at_checkout` (PHASE-9 §4's eval golden set:
    "paths that only appear end-to-end") skips `submit_booking_draft` and settles TRANSACT on
    `booking_status="abandoned"` instead -- a real terminal status `phase_machine.py` already
    recognised (`TRANSACT_TERMINAL_STATUSES`) but nothing had driven a session into before.

    Every phase this run visits produces one OpenTelemetry span (PHASE-9 §3), all children of
    a single `session` span -- gate 9.1's "one trace containing spans for all four phases".
    """
    configure_tracing()
    store = store or InMemoryListingStore.seeded()
    extractor = extractor or DemoSlotExtractor()
    state = new_session(session_id or str(uuid.uuid4()))
    result = DemoRunResult(
        state=state, audit_log=AuditLog(), journal=journal or InMemoryDecisionJournal()
    )
    lookup: StateLookup = lambda sid: result.state if sid == result.state.session_id else None  # noqa: E731
    audit_hook = build_audit_hook(result.audit_log, result.state.session_id, lookup)

    async def record_turn(tool_name: str, tool_input: dict[str, object]) -> None:
        # Gate 9.2: every tool call gets a span with an args hash and a duration, nested
        # under whichever phase span is currently ambient -- this closure is the one place
        # every tool call in a demo session passes through, live-path's audit hook mirror.
        with tool_call_span(tool_name, tool_input):
            await audit_hook(
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": result.state.session_id,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "transcript_path": "",
                    "cwd": "",
                    "tool_use_id": "",
                },
                None,
                {"signal": None},
            )

    tracer = get_tracer()
    session_span = tracer.start_span("session", attributes={"session.id": result.state.session_id})
    with trace.use_span(session_span, end_on_exit=True):
        # -- INTERVIEW ----------------------------------------------------------------------
        with phase_span(Phase.INTERVIEW) as span:
            turns_before = result.state.total_turns
            for utterance in utterances:
                if result.state.phase is not Phase.INTERVIEW:
                    break
                await record_turn("interview_turn", {"utterance": utterance})
                result.state = await process_turn(result.state, utterance, extractor)
                result.phase_history.append(result.state.phase)
            span.set_attribute("phase.turns", result.state.total_turns - turns_before)
            span.set_attribute(
                "phase.exit_predicate_met", result.state.phase is not Phase.INTERVIEW
            )

        # -- RESEARCH -------------------------------------------------------------------------
        await _run_research_until_exit(result, store, lookup, record_turn)

        # -- RECOMMEND: a mid-phase constraint change loops back to RESEARCH (gate 3.5) -------
        if result.state.phase is Phase.RECOMMEND and mid_recommend_utterance is not None:
            await record_turn("interview_turn", {"utterance": mid_recommend_utterance})
            result.state = await process_turn(result.state, mid_recommend_utterance, extractor)
            result.phase_history.append(result.state.phase)
            await _run_research_until_exit(result, store, lookup, record_turn)

        if result.state.phase is Phase.RECOMMEND:
            with phase_span(Phase.RECOMMEND) as span:
                candidates = result.state.candidate_ids
                listings = await _fetch_candidates(store, candidates)
                listings_by_id = {listing.id: listing for listing in listings}

                with scoring_span(
                    candidate_count=len(listings), seed=result.state.session_id
                ) as scoring_span_obj:
                    ranking_result = rank(listings, result.state.profile)
                    for criterion, weight in ranking_result.weights.as_dict().items():
                        scoring_span_obj.set_attribute(f"scoring.weight.{criterion}", weight)
                    determinism_hash = hashlib.sha256(
                        "".join(r.model_dump_json() for r in ranking_result.ranked).encode()
                    ).hexdigest()
                    scoring_span_obj.set_attribute("scoring.determinism_hash", determinism_hash)

                survivors, violations = critic_pass(
                    ranking_result.ranked, listings_by_id, result.state.profile
                )
                result.ranking_result = ranking_result
                result.critic_survivors = survivors
                result.critic_violations = violations

                selected: str | None = None
                if survivors:
                    top_listing = listings_by_id[survivors[0].listing_id]
                    selected = f"{top_listing.source}:{top_listing.source_id}"
                await _record_recommendation(
                    result, candidates, selected, ranking_result, survivors, violations
                )
                result.state = result.state.model_copy(
                    update={
                        "ranked": True,
                        "selected_candidate": selected,
                        "disengaged": selected is None,
                    }
                )
                result.state = advance(result.state)
                result.phase_history.append(result.state.phase)
                span.set_attribute("phase.exit_predicate_met", True)

        # -- TRANSACT ---------------------------------------------------------------------
        if result.state.phase is Phase.TRANSACT and result.state.selected_candidate is not None:
            with phase_span(Phase.TRANSACT) as span:
                await record_turn(
                    "open_booking_form", {"source_id": result.state.selected_candidate}
                )
                if decline_at_checkout:
                    result.state = result.state.model_copy(update={"booking_status": "abandoned"})
                else:
                    await record_turn("submit_booking_draft", {})
                    result.state = result.state.model_copy(
                        update={"booking_status": "draft_submitted"}
                    )
                result.state = advance(result.state)
                result.phase_history.append(result.state.phase)
                span.set_attribute("phase.exit_predicate_met", True)

    return result


async def _fetch_candidates(store: ListingStore, candidate_ids: tuple[str, ...]) -> list[Listing]:
    """`candidate_ids` are `"source:source_id"` strings (`research.py`'s own format) -- resolve
    each back to the full `Listing` P5's ranking engine needs (it scores structured fields,
    never the summary RESEARCH carried).
    """
    listings: list[Listing] = []
    for candidate_id in candidate_ids:
        source, source_id = candidate_id.split(":", 1)
        listing = await store.fetch(source, source_id)
        if listing is not None:
            listings.append(listing)
    return listings


async def _record_recommendation(
    result: DemoRunResult,
    candidates: tuple[str, ...],
    selected: str | None,
    ranking_result: RankingResult,
    survivors: tuple[RankedResult, ...],
    violations: tuple[str, ...],
) -> None:
    """Writes the `DecisionEntry`s `explain()` reads back verbatim for gate 4.3.

    P3's RECOMMEND used to be a placeholder -- "first surviving candidate", not a real score
    (PHASE-3 §2 put scoring out of scope). P5's `rank()` + `critic_pass()` now do the real
    work; this function's only job is recording what they decided, through the exact same
    `DecisionEntry` shape D-019 already wired the journal for -- no schema or gate-mechanism
    change, just a rationale that is now actually a scored one.
    """
    weights_rationale = ", ".join(
        f"{w.criterion}={w.weight:.2f}" for w in ranking_result.weights.weights
    )
    await result.journal.record(
        DecisionEntry(
            id=uuid.uuid4(),
            session_id=session_uuid(result.state.session_id),
            turn=result.state.total_turns,
            kind=DecisionKind.WEIGHTS_CHOSEN,
            inputs_hash=compute_inputs_hash({"weights": ranking_result.weights.as_dict()}),
            weights=ranking_result.weights.as_dict(),
            outcome={"criteria": [w.criterion for w in ranking_result.weights.weights]},
            rationale=f"DEMO_MODE fixed weights: {weights_rationale}",
            ts=datetime.now(UTC),
        )
    )

    if selected is not None and survivors:
        rationale = survivors[0].rationale
    elif ranking_result.ranked:
        rationale = (
            "every ranked candidate failed the critic's re-check against hard filters and "
            f"the stated budget ({len(violations)} violation(s)); RECOMMEND has zero "
            "survivors even though RESEARCH returned candidates."
        )
    else:
        rationale = (
            "no candidate survived RESEARCH's hard filters within budget; RECOMMEND was "
            "forced open with zero candidates (SessionState.infeasible)."
        )
    inputs_hash = compute_inputs_hash(
        {
            "session_id": result.state.session_id,
            "candidates": list(candidates),
            "profile": result.state.profile.model_dump(mode="json"),
            "weights": ranking_result.weights.as_dict(),
        }
    )
    await result.journal.record(
        DecisionEntry(
            id=uuid.uuid4(),
            session_id=session_uuid(result.state.session_id),
            turn=result.state.total_turns,
            kind=DecisionKind.RECOMMENDATION_MADE,
            inputs_hash=inputs_hash,
            weights=ranking_result.weights.as_dict(),
            outcome={
                "selected": selected,
                "candidates_considered": list(candidates),
                "critic_violations": list(violations),
            },
            rationale=rationale,
            ts=datetime.now(UTC),
        )
    )


async def _run_research_until_exit(
    result: DemoRunResult, store: ListingStore, lookup: StateLookup, record_turn: RecordTurn
) -> None:
    """Every pass through RESEARCH: gate the search, dispatch both researchers concurrently,
    fold their candidates in, then let the phase machine decide whether to advance.

    One `phase.research` span per *call* (a session revisiting RESEARCH after a backward
    transition calls this twice, and gets two spans -- `run_demo_session`'s own docstring on
    why that's the honest shape). Opened only once there is actually a RESEARCH stay to
    trace, not unconditionally, since a session whose INTERVIEW never advanced would
    otherwise get a span for a phase it never entered.
    """
    if result.state.phase is not Phase.RESEARCH:
        return
    with phase_span(Phase.RESEARCH) as span:
        turns_before = result.state.total_turns
        while result.state.phase is Phase.RESEARCH:
            # Spends one RESEARCH turn per pass -- without this, a profile that never turns up
            # a candidate would leave `turn_in_phase` at 0 forever and `budget_exhausted` would
            # never fire, looping this `while` indefinitely instead of forcing the exit to
            # RECOMMEND that PHASE-3 §3's turn budget exists to guarantee.
            result.state = begin_turn(result.state)
            search_gate = build_search_gate(result.state.session_id, lookup)
            decision = await search_gate("search_cars", {}, ToolPermissionContext())
            if decision.behavior != "allow":
                result.search_denied_before_two_slots = True
                span.set_attribute("phase.turns", result.state.total_turns - turns_before)
                span.set_attribute("phase.exit_predicate_met", False)
                return
            await record_turn("search_cars", {})
            # Sibling researcher spans (gate 9.3) nest under this one -- `dispatch_researchers`
            # runs its `asyncio.gather` while `phase.research` is the ambient current span, so
            # every task it launches snapshots this as its parent.
            traces = await dispatch_researchers(
                store, result.state.profile, simulated_latency_s=RESEARCH_SIMULATED_LATENCY_S
            )
            result.research_traces = traces
            candidate_ids = tuple(cid for trace in traces for cid in trace.candidate_ids)
            result.state = result.state.model_copy(update={"candidate_ids": candidate_ids})
            result.state = advance(result.state)
            result.phase_history.append(result.state.phase)
        span.set_attribute("phase.turns", result.state.total_turns - turns_before)
        span.set_attribute("phase.exit_predicate_met", len(result.state.candidate_ids) >= 1)
