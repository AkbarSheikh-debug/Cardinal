"""Streams `DEMO_MODE`'s flow through the real transport (PHASE-11 SS3/SS7, gates 11.3/11.4).

`src/agent/demo.py`'s `run_demo_session` is what gates 3/4/5/9/10 assert against, and it never
touches `ui-mcp`/`booking-mcp` at all -- it mutates `SessionState` directly and records tool
*names* to the audit log, which is enough for those gates but produces nothing a browser could
render. Before this module, `DEMO_MODE` had no path to the actual web app: nothing pushed a
single A2UI message through a session's `UISink`, so the SSE canvas showed nothing and a judge
running `docker compose up` would see an empty page.

This module closes that gap by calling the *real* `render_progress`/`render_tco`/
`render_results`/`render_detail` (`src/mcp/ui/tools.py`) and `open_booking_form`/
`submit_booking_draft`/`open_checkout` (`src/mcp/booking/tools.py`) handlers directly --
`ToolSpec.sdk_tool.handler`, the exact async function a live model's tool call would invoke --
sequenced by a script instead of a model's decisions. It reuses the same phase machine,
interview extractor, research dispatcher, and P5 ranking/critic engine `run_demo_session` does,
so every number it shows is real, not a fixture. It never constructs a `ClaudeSDKClient`,
so it stays inside DECISIONS.md D-015's boundary: this is delivery wiring for a scripted replay,
not a live model rehearsal.

`confirm_booking` is deliberately never called from here (CONSTITUTION I.2) -- this module gets
a session to an opened checkout and stops. The confirm click has to be a real, trusted browser
event, same as any other session.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.adapters.store import ListingStore
from src.agent.extraction import DemoSlotExtractor
from src.agent.interview import process_turn
from src.agent.journal import (
    DecisionJournal,
    InMemoryDecisionJournal,
    compute_inputs_hash,
    session_uuid,
)
from src.agent.phase_machine import Phase, SessionState, advance, begin_turn, new_session
from src.agent.research import dispatch_researchers
from src.domain.listing import Listing
from src.domain.marketplace import MAX_PAGE_SIZE, SearchQuery
from src.domain.memory import DecisionEntry, DecisionKind
from src.domain.ranking import RankingResult, critic_pass, rank
from src.domain.tco import TcoComparison, compute_comparison
from src.mcp.audience import for_audience
from src.mcp.booking.tools import build_tool_specs as build_booking_tool_specs
from src.mcp.ui.sink import UISink
from src.mcp.ui.surfaces import SurfaceRegistry
from src.mcp.ui.tools import build_tool_specs as build_ui_tool_specs

#: "Family Fatima" from `tests/fixtures/demo/personas.json` (gate 3.1) -- a real, already-proven
#: four-turn persona rather than a bespoke demo-only script, so this path exercises the same
#: extraction behaviour the gates already check.
DEMO_UTTERANCES: tuple[str, ...] = (
    "we need a family car",
    "we're planning to buy, not rent",
    "budget is 30000 euros",
    "we must be ready by 2026-08-30",
)

#: Cardinal's own reply to each `DEMO_UTTERANCES` line, pushed to the chat rail alongside the
#: canvas update it already produced (D-063). Before this, `run_streamed_demo` only ever
#: pushed `render_*` surfaces -- every beat updated the canvas and the chat rail stayed
#: completely silent for the whole seven-beat walkthrough, which is what actually prompted
#: this: a viewer watching charts appear with no narration reads as "not much is happening"
#: regardless of how much real computation backs each one.
DEMO_REPLIES: tuple[str, ...] = (
    "A family car -- got it. Are you looking to buy or rent, and what's your budget?",
    "Buying it is. What's your budget, and by when do you need it?",
    "€30,000 noted. Last thing -- by when do you need it?",
    "That's everything I need. Before I search, let me check whether buying or renting "
    "actually works out cheaper for a car like this.",
)

TCO_HORIZON_MONTHS = 36

#: Paced for a human (or Playwright) watching the SSE stream to see each beat land distinctly,
#: not a functional requirement -- 0 would still be correct, just instant.
BEAT_PAUSE_S = 0.5


@dataclass
class DemoStreamContext:
    """What the 'explain' action round-trip (a click on a rendered `CarCard`, PHASE-6 SS6)
    needs to answer without recomputing anything -- module-scope for the session's lifetime,
    the same posture `src/mcp/booking/tools.py`'s own `_booking_drafts` already takes and for
    the same reason: a fresh instance per call would forget what an earlier call just did.
    """

    ranking_result: RankingResult
    listings_by_id: dict[UUID, Listing]
    booking_draft_id: str | None = None


_contexts: dict[str, DemoStreamContext] = {}

#: Beat 2's real `TcoComparison` + the listing it was computed for, keyed by session -- kept
#: separate from `DemoStreamContext` rather than added to it, because beat 2 (TCO) runs before
#: beat 4 (RECOMMEND) is what actually creates that dataclass's instance; a second small dict
#: is less disruptive than making `DemoStreamContext`'s existing fields optional for every
#: consumer of `handle_explain_action` to re-check. Mirrors D-026: `handle_expand_tco_action`
#: below reads the same `TcoComparison` beat 2 already computed, never a second one.
_tco_contexts: dict[str, tuple[TcoComparison, Listing]] = {}


def context_for(session_id: str) -> DemoStreamContext | None:
    return _contexts.get(session_id)


def forget(session_id: str) -> None:
    _contexts.pop(session_id, None)
    _tco_contexts.pop(session_id, None)


async def _fetch_candidates(store: ListingStore, candidate_ids: tuple[str, ...]) -> list[Listing]:
    listings: list[Listing] = []
    for candidate_id in candidate_ids:
        source, source_id = candidate_id.split(":", 1)
        listing = await store.fetch(source, source_id)
        if listing is not None:
            listings.append(listing)
    return listings


async def _dual_offer_listing(store: ListingStore) -> Listing | None:
    """A listing the catalogue generator itself gives both a buy price and rental rates --
    PHASE-1's 20 'both' rows, all seeded onto `mock_drivenow` (PROGRESS.md's Phase 1 entry:
    "MockDriveNow carries all 90 rent plus all 20 both"). Real numbers for the rent-vs-buy
    break-even beat, not a fixture; `None` only if the catalogue itself ever stopped seeding
    any dual-offer rows, in which case this beat is skipped rather than crashing the demo.

    Paginated at `MAX_PAGE_SIZE` (CONSTITUTION II.7: search results are bounded, no exception
    for this module) -- `mock_drivenow` carries 110 rows total, so the 20 'both' ones are not
    guaranteed to land on a single page sorted by price.
    """
    page = 1
    while True:
        query = SearchQuery(page=page, page_size=MAX_PAGE_SIZE)
        listings, total = await store.query(query, sources=("mock_drivenow",))
        if not listings:
            return None
        for listing in listings:
            if listing.price_buy is not None and listing.rental_rates is not None:
                return listing
        if page * MAX_PAGE_SIZE >= total:
            return None
        page += 1


async def _record_recommendation_decision(
    journal: DecisionJournal,
    state: SessionState,
    ranking_result: RankingResult,
    survivors: tuple[Any, ...],
    violations: tuple[str, ...],
    selected: str | None,
) -> None:
    """Same `DecisionEntry` shape `demo.py`'s `_record_recommendation` writes (D-019) -- the
    'trace' beat's `explain()` call reads this back verbatim, zero recomputation, gate 4.3's
    mechanism reused rather than re-derived here.
    """
    weights_rationale = ", ".join(
        f"{w.criterion}={w.weight:.2f}" for w in ranking_result.weights.weights
    )
    await journal.record(
        DecisionEntry(
            id=uuid.uuid4(),
            session_id=session_uuid(state.session_id),
            turn=state.total_turns,
            kind=DecisionKind.WEIGHTS_CHOSEN,
            inputs_hash=compute_inputs_hash({"weights": ranking_result.weights.as_dict()}),
            weights=ranking_result.weights.as_dict(),
            outcome={"criteria": [w.criterion for w in ranking_result.weights.weights]},
            rationale=f"DEMO_MODE fixed weights: {weights_rationale}",
            ts=datetime.now(UTC),
        )
    )
    rationale = (
        survivors[0].rationale
        if selected is not None and survivors
        else (
            f"every ranked candidate failed the critic's re-check ({len(violations)} violation(s))."
        )
    )
    await journal.record(
        DecisionEntry(
            id=uuid.uuid4(),
            session_id=session_uuid(state.session_id),
            turn=state.total_turns,
            kind=DecisionKind.RECOMMENDATION_MADE,
            inputs_hash=compute_inputs_hash(
                {
                    "session_id": state.session_id,
                    "candidates": list(state.candidate_ids),
                    "weights": ranking_result.weights.as_dict(),
                }
            ),
            weights=ranking_result.weights.as_dict(),
            outcome={"selected": selected, "critic_violations": list(violations)},
            rationale=rationale,
            ts=datetime.now(UTC),
        )
    )


def _progress_args(state: SessionState, trace: list[str]) -> dict[str, Any]:
    return {
        "completed_slots": [
            name for name in state.profile.REQUIRED if getattr(state.profile, name).is_filled
        ],
        "open_slots": state.profile.missing_slots(),
        "reasoning_trace": trace,
    }


async def run_streamed_demo(
    session_id: str,
    *,
    store: ListingStore,
    sink: UISink,
    registry: SurfaceRegistry,
    journal: DecisionJournal | None = None,
) -> SessionState:
    """Drives one persona through INTERVIEW -> RESEARCH -> RECOMMEND -> TRANSACT, pushing a
    real A2UI/MCP-App message for every beat PHASE-11 SS6 names except the trusted confirm
    click, which this module never performs (CONSTITUTION I.2).
    """
    journal = journal or InMemoryDecisionJournal()
    extractor = DemoSlotExtractor()
    state = new_session(session_id)

    # `for_audience` is the same choke point a live session's tool dispatch goes through
    # (gate 9.2's tracing wrapper) -- calling handlers straight off `ToolSpec` would skip it.
    # "model" for ui-mcp (all five tools are MODEL_ONLY); "app" for booking-mcp, since this
    # script is standing in for the *view* submitting a form, not the model calling a tool.
    ui_tools = {
        t.name: t.handler
        for t in for_audience(
            build_ui_tool_specs(
                session_id=session_id,
                sink=sink,
                registry=registry,
                store=store,
                phase=lambda: state.phase.value,
            ),
            "model",
        )
    }
    booking_tools = {
        t.name: t.handler
        for t in for_audience(
            build_booking_tool_specs(session_id=session_id, sink=sink, store=store), "app"
        )
    }

    # -- Beat 1: interview ------------------------------------------------------------------
    for utterance, reply in zip(DEMO_UTTERANCES, DEMO_REPLIES, strict=True):
        if state.phase is not Phase.INTERVIEW:
            break
        await sink.push([{"kind": "user_text", "text": utterance}])
        state = await process_turn(state, utterance, extractor)
        await ui_tools["render_progress"](_progress_args(state, [f'heard: "{utterance}"']))
        await sink.push([{"kind": "agent_text", "text": reply}])
        await asyncio.sleep(BEAT_PAUSE_S)

    # -- Beat 2: rent-vs-buy break-even, ahead of RESEARCH so the maths lands before the
    # marketplaces answer -------------------------------------------------------------------
    dual = await _dual_offer_listing(store)
    if dual is not None:
        comparison = compute_comparison(dual, TCO_HORIZON_MONTHS)
        _tco_contexts[session_id] = (comparison, dual)
        tco_args: dict[str, Any] = {
            "horizon_months": TCO_HORIZON_MONTHS,
            "items": [
                {
                    "source": dual.source,
                    "source_id": dual.source_id,
                    "total_cost_eur": float(comparison.buy.total.amount),
                }
            ],
        }
        if comparison.break_even_month is not None:
            tco_args["break_even_month"] = comparison.break_even_month
        await ui_tools["render_tco"](tco_args)
        break_even_note = (
            f" It breaks even around month {comparison.break_even_month}."
            if comparison.break_even_month is not None
            else ""
        )
        await sink.push(
            [
                {
                    "kind": "agent_text",
                    "text": f"Here's the real number, not an estimate.{break_even_note}",
                }
            ]
        )
        await asyncio.sleep(BEAT_PAUSE_S)

    # -- Beat 3: parallel research ------------------------------------------------------------
    if state.phase is Phase.RESEARCH:
        await sink.push(
            [{"kind": "agent_text", "text": "Searching both marketplaces at once now."}]
        )
    while state.phase is Phase.RESEARCH:
        state = begin_turn(state)
        await ui_tools["render_progress"](
            _progress_args(state, ["searching mock_autobazaar and mock_drivenow in parallel..."])
        )
        traces = await dispatch_researchers(store, state.profile, simulated_latency_s=0.05)
        candidate_ids = tuple(cid for t in traces for cid in t.candidate_ids)
        state = state.model_copy(update={"candidate_ids": candidate_ids})
        state = advance(state)
    await asyncio.sleep(BEAT_PAUSE_S)

    # -- Beat 4: ranked results, real P5 scoring + critic pass --------------------------------
    if state.phase is Phase.RECOMMEND:
        listings = await _fetch_candidates(store, state.candidate_ids)
        listings_by_id = {listing.id: listing for listing in listings}
        ranking_result = rank(listings, state.profile)
        survivors, violations = critic_pass(ranking_result.ranked, listings_by_id, state.profile)
        _contexts[session_id] = DemoStreamContext(
            ranking_result=ranking_result, listings_by_id=listings_by_id
        )

        display = survivors or ranking_result.ranked[:3]
        if display:
            await ui_tools["render_results"](
                {
                    "weights": ranking_result.weights.as_dict(),
                    "items": [
                        {
                            "source": listings_by_id[r.listing_id].source,
                            "source_id": listings_by_id[r.listing_id].source_id,
                            "rank": i + 1,
                            "score": r.breakdown.total,
                            "rationale": r.rationale,
                        }
                        for i, r in enumerate(display)
                    ],
                }
            )
            await sink.push(
                [
                    {
                        "kind": "agent_text",
                        "text": "Here's what I found, ranked and scored -- not just sorted by "
                        "price. Click any card to see exactly why it landed where it did.",
                    }
                ]
            )
        await asyncio.sleep(BEAT_PAUSE_S)

        selected: str | None = None
        # The top-ranked survivor is not necessarily buy-eligible: `_reference_price` (P5's
        # ranking.py) falls back to `market_value` for a rent-only listing surfaced under a
        # buy goal, so it can rank and display a price without ever supporting a purchase
        # quote. The booking/checkout beat needs a listing `adapter.quote()` can actually
        # price as a purchase -- the first survivor, in rank order, that has one.
        buy_eligible = next(
            (r for r in survivors if listings_by_id[r.listing_id].price_buy is not None), None
        )
        if buy_eligible is not None:
            top = listings_by_id[buy_eligible.listing_id]
            selected = f"{top.source}:{top.source_id}"
            # -- Beat 5: powertrain explainer for the winner ---------------------------------
            await ui_tools["render_detail"](
                {
                    "source": top.source,
                    "source_id": top.source_id,
                    "show_powertrain_explainer": True,
                }
            )
            await sink.push(
                [
                    {
                        "kind": "agent_text",
                        "text": "And here's a closer look at what's under the hood "
                        "of the top pick.",
                    }
                ]
            )
            await asyncio.sleep(BEAT_PAUSE_S)

        await _record_recommendation_decision(
            journal, state, ranking_result, survivors, violations, selected
        )
        state = state.model_copy(
            update={"ranked": True, "selected_candidate": selected, "disengaged": selected is None}
        )
        state = advance(state)

    # -- Beat 6: booking App -- opened here, then this function stops. A human (or Playwright,
    # standing in for one) fills the real form and clicks Submit for real; `on_draft_submitted`
    # below reacts to that real RPC and opens checkout next. Auto-submitting it from here would
    # make "booking App" a beat nobody actually touched, not a real interaction.
    if state.phase is Phase.TRANSACT and state.selected_candidate is not None:
        source, source_id = state.selected_candidate.split(":", 1)
        await sink.push(
            [
                {
                    "kind": "agent_text",
                    "text": "Let's get this booked. Fill in your details below and I'll take "
                    "it from there.",
                }
            ]
        )
        await booking_tools["open_booking_form"](
            {"source": source, "source_id": source_id, "offer_type": "buy"}
        )

    return state


async def on_draft_submitted(
    session_id: str, *, sink: UISink, store: ListingStore, draft_id: str
) -> None:
    """Beat 7: a real `submit_booking_draft` RPC just succeeded (a human's real click inside
    the sandboxed booking-form iframe, PHASE-7's own mechanism) -- open checkout next, priced
    fresh by the real adapter, the same way a live model would react to the form having been
    submitted. `confirm_booking` is still never called from anywhere in this module
    (CONSTITUTION I.2); this only gets a session to an opened checkout.

    A no-op outside `DEMO_MODE` and outside a session this module actually started -- callers
    only invoke this after checking `demo_mode()` themselves (`src/api/main.py`).
    """
    booking_tools = {
        t.name: t.handler
        for t in for_audience(
            build_booking_tool_specs(session_id=session_id, sink=sink, store=store), "app"
        )
    }
    ctx = _contexts.get(session_id)
    if ctx is not None:
        ctx.booking_draft_id = draft_id
    await sink.push(
        [
            {
                "kind": "agent_text",
                "text": "Submitted. Now let's get you checked out -- priced fresh, right here.",
            }
        ]
    )
    await booking_tools["open_checkout"]({"booking_draft_id": draft_id})


async def handle_expand_tco_action(
    session_id: str, *, sink: UISink, registry: SurfaceRegistry
) -> bool:
    """The 'expanded the cost radar' beat: a click on the TCO surface's own expand affordance
    (`TcoChart`'s `context.dispatchAction`, catalog.tsx) reaches here the same way `explain`
    does for a `CarCard`, and pushes the same `TcoComparison` beat 2 already computed --
    `compile_tco_breakdown_surface` (D-026's no-recomputation rule, reused a second time).
    """
    from src.mcp.ui.compiler import compile_tco_breakdown_surface, to_messages

    ctx = _tco_contexts.get(session_id)
    if ctx is None:
        return False
    comparison, listing = ctx
    compiled = compile_tco_breakdown_surface(
        comparison, source=listing.source, source_id=listing.source_id
    )
    await sink.push(to_messages(session_id, compiled, registry))
    return True


async def handle_explain_action(
    session_id: str, *, sink: UISink, registry: SurfaceRegistry, payload: dict[str, Any]
) -> bool:
    """The 'opened a score breakdown' beat: a real click on a rendered `CarCard` (PHASE-6 SS6's
    action round-trip) reaches here via `POST /sessions/{id}/actions`, and this pushes the same
    `ScoreBreakdown` `rank()` already computed -- no recomputation (D-026's rule, reused).
    Returns whether it recognised and handled the action, so the caller knows whether to fall
    back to filing it as a plain user turn instead.
    """
    from src.mcp.ui.compiler import compile_score_breakdown_surface, to_messages

    ctx = _contexts.get(session_id)
    if ctx is None:
        return False
    source_id = payload.get("sourceId") or payload.get("source_id")
    source = payload.get("source")
    match = next(
        (
            result
            for result in ctx.ranking_result.ranked
            if ctx.listings_by_id.get(result.listing_id) is not None
            and ctx.listings_by_id[result.listing_id].source_id == source_id
            and (source is None or ctx.listings_by_id[result.listing_id].source == source)
        ),
        None,
    )
    if match is None:
        return False
    listing = ctx.listings_by_id[match.listing_id]
    compiled = compile_score_breakdown_surface(
        match.breakdown, source=listing.source, source_id=listing.source_id
    )
    await sink.push(to_messages(session_id, compiled, registry))
    return True
