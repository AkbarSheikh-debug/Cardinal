"""The eval harness (PHASE-9 §4): every metric in PHASE-9's own table, computed for real
against `DEMO_MODE`'s code paths -- extraction, the phase machine, guardrails, `rank()`,
`critic_pass()` -- across a 30-persona golden set in one headless run. Gate 9.4/9.5's "scored
report" is this module's `EvalReport`.

Two of the nine metrics ask a question `DEMO_MODE` structurally can't answer the way a live
multi-turn agentic session would, and this module says so rather than fabricating a number:

- **Tool-call rate.** PHASE-9 §4 means "searches per session"; `DEMO_MODE`'s RESEARCH phase
  issues exactly one `search_cars` audit entry per turn-in-phase no matter how many of the
  two marketplaces it fans out to underneath (the model never learns marketplaces are plural,
  D-013, and that holds inside `DEMO_MODE` too). Counting *every* audited tool call in a
  session -- interview turns, searches, booking calls -- keeps faith with what the metric is
  actually for (catching a session that never reaches for a tool at all) without overstating
  what a scripted, non-agentic replay can measure.
- **Cost per session.** `DEMO_MODE` makes zero model calls by construction
  (CONSTITUTION III.7) -- the honest number is $0.00, not an estimate against published
  per-token rates for calls that never happened. A live rehearsal (PROGRESS.md's own "Next"
  list) is what would give this metric something real to price per role.

Escape-hatch ratio is measured against a real render: each persona with survivors has its top
3 compiled through `compile_results_surface` (P6's real, deterministic compiler) the way a
live `render_results` tool call would drive it, then counted alongside zero `compose_surface`
calls -- `DEMO_MODE` has no model to reach for the escape hatch with, so the ratio is
genuinely, structurally 0/N, not assumed to be zero.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from src.adapters.store import InMemoryListingStore, ListingStore
from src.agent.demo import run_demo_session
from src.domain.enums import OfferType
from src.domain.listing import Listing
from src.domain.profile import RequirementProfile
from src.domain.ranking import UNVERIFIED_MARKER, hard_filter_passes
from src.mcp.ui.compiler import compile_results_surface

PROFILE_COMPLETENESS_THRESHOLD = 0.95
PRECISION_AT_3_THRESHOLD = 0.80
GROUNDEDNESS_THRESHOLD = 1.00
TOOL_CALL_RATE_RANGE = (2, 8)
COST_PER_SESSION_THRESHOLD_USD = 0.40
ESCAPE_HATCH_RATIO_THRESHOLD = 0.15
LATENCY_P50_THRESHOLD_S = 8.0
LATENCY_P95_THRESHOLD_S = 25.0


@dataclass(frozen=True)
class PersonaEvalResult:
    name: str
    expect_infeasible: bool
    reached_infeasible: bool
    profile_completeness: float
    precision_at_3: float | None
    groundedness: float | None
    constraint_violations: int
    guardrail_violations: int
    escape_hatch_calls: int
    render_calls: int
    tool_call_count: int
    latency_s: float
    cost_usd: float


@dataclass(frozen=True)
class MetricSummary:
    name: str
    value: float
    threshold: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class EvalReport:
    personas: tuple[PersonaEvalResult, ...]
    #: PHASE-9 §4's nine named metrics -- `all_passed` gates on exactly these.
    metrics: tuple[MetricSummary, ...]
    #: Diagnostic, not a PHASE-9 §4 metric: personas whose `expect_infeasible` fixture flag
    #: disagreed with what the run actually reached. Reused P5 personas (`golden_set.json`)
    #: carry no such flag at all (defaults `False`) even though gate 5.4 already establishes
    #: one of the twenty is genuinely infeasible against the seeded catalogue -- surfaced here
    #: for transparency rather than silently hard-coding that persona's name as an exception,
    #: which would go stale the moment the catalogue seed or generator changes (D-002's own
    #: reasoning about not baking a generator-dependent fact into a hand-picked exception).
    infeasible_mismatches: tuple[str, ...] = ()

    @property
    def all_passed(self) -> bool:
        return all(m.passed for m in self.metrics)

    def metric(self, name: str) -> MetricSummary:
        return next(m for m in self.metrics if m.name == name)


def _satisfies_profile(listing: Listing, profile: RequirementProfile) -> bool:
    """The same structural self-consistency check gate 5.4 (D-024) uses -- does a survivor
    independently satisfy the persona's *own* final stated constraints -- reimplemented here
    rather than imported from `scripts/gate_phase5.py`, which is a script, not a library.
    Feeds `precision_at_3`; includes the requested category, which "constraint violation" in
    PHASE-9 §4's sense does not (a mismatched category is a ranking-quality problem, not a
    violated hard filter or budget).
    """
    requested_categories = {c.value for c in (profile.category.value or [])}
    if requested_categories and listing.category.value not in requested_categories:
        return False
    return not _violates_constraints(listing, profile)


def _violates_constraints(listing: Listing, profile: RequirementProfile) -> bool:
    """PHASE-9 §4's "results violating a stated hard filter": every generic `HardFilter`
    (gate 5.3's mechanism, `hard_filter_passes`) plus the two constraints `critic_pass`
    itself checks (D-022) -- budget for a buy goal, availability against the target date.
    Run again here, independently, against whatever reached the final top-3 (which already
    passed through `critic_pass` once in `demo.py`'s RECOMMEND block) -- a second,
    separately-written check in D-024's style, not a re-read of the critic's own verdict.
    """
    if any(not hard_filter_passes(listing, hf) for hf in profile.hard_filters):
        return True
    budget = profile.budget.value
    if budget is not None and profile.goal.value is not OfferType.RENT:
        price = (listing.price_buy or listing.market_value).amount
        if price > budget.amount:
            return True
    target_date = profile.target_date.value
    if target_date is not None and listing.available_from > target_date:
        return True
    return False


async def _listings_by_id(
    store: ListingStore, candidate_ids: tuple[str, ...]
) -> dict[uuid.UUID, Listing]:
    listings: dict[uuid.UUID, Listing] = {}
    for candidate_id in candidate_ids:
        source, source_id = candidate_id.split(":", 1)
        listing = await store.fetch(source, source_id)
        if listing is not None:
            listings[listing.id] = listing
    return listings


async def _eval_one_persona(persona: dict[str, Any], store: ListingStore) -> PersonaEvalResult:
    started = time.perf_counter()
    result = await run_demo_session(
        list(persona["utterances"]),
        store=store,
        session_id=f"eval-{persona['name']}",
        mid_recommend_utterance=persona.get("mid_recommend_utterance"),
        decline_at_checkout=bool(persona.get("decline_at_checkout", False)),
    )
    latency_s = time.perf_counter() - started

    top3 = result.critic_survivors[:3]
    precision_at_3: float | None = None
    groundedness: float | None = None
    result_violations = 0
    escape_hatch_calls = 0
    render_calls = 0
    if top3:
        listings_by_id = await _listings_by_id(store, result.state.candidate_ids)
        hits = sum(
            1
            for r in top3
            if r.listing_id in listings_by_id
            and _satisfies_profile(listings_by_id[r.listing_id], result.state.profile)
        )
        precision_at_3 = hits / len(top3)
        grounded_hits = sum(1 for r in top3 if not r.rationale.startswith(UNVERIFIED_MARKER))
        groundedness = grounded_hits / len(top3)
        result_violations = sum(
            1
            for r in top3
            if r.listing_id in listings_by_id
            and _violates_constraints(listings_by_id[r.listing_id], result.state.profile)
        )

        # A real compiled render of these results (P6's deterministic compiler, the same one
        # a live `render_results` tool call would drive) -- not the `compose_surface` escape
        # hatch, which `DEMO_MODE` has no model to call in the first place.
        compile_results_surface(
            {
                "items": [
                    {
                        "source": listings_by_id[r.listing_id].source,
                        "source_id": listings_by_id[r.listing_id].source_id,
                        "rank": r.rank,
                        "score": r.breakdown.total,
                        "rationale": r.rationale,
                    }
                    for r in top3
                    if r.listing_id in listings_by_id
                ]
            }
        )
        render_calls = 1

    return PersonaEvalResult(
        name=persona["name"],
        expect_infeasible=bool(persona.get("expect_infeasible", False)),
        reached_infeasible=result.state.infeasible or not top3,
        profile_completeness=result.state.profile.completeness,
        precision_at_3=precision_at_3,
        groundedness=groundedness,
        constraint_violations=result_violations,
        guardrail_violations=1 if result.search_denied_before_two_slots else 0,
        escape_hatch_calls=escape_hatch_calls,
        render_calls=render_calls,
        tool_call_count=len(result.audit_log.for_session(result.state.session_id)),
        latency_s=latency_s,
        cost_usd=0.0,  # DEMO_MODE: zero model calls, CONSTITUTION III.7
    )


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct * (len(ordered) - 1))))
    return ordered[index]


def _summarise(personas: tuple[PersonaEvalResult, ...]) -> tuple[MetricSummary, ...]:
    feasible = [p for p in personas if not p.expect_infeasible]
    graded = [p for p in feasible if p.precision_at_3 is not None]

    completeness = sum(p.profile_completeness for p in personas) / len(personas)
    precision = (
        sum(p.precision_at_3 for p in graded if p.precision_at_3 is not None) / len(graded)
        if graded
        else 1.0
    )
    grounded = [p for p in graded if p.groundedness is not None]
    groundedness = (
        sum(p.groundedness for p in grounded if p.groundedness is not None) / len(grounded)
        if grounded
        else 1.0
    )
    total_violations = sum(p.constraint_violations for p in personas)
    total_guardrail = sum(p.guardrail_violations for p in personas)
    total_escape = sum(p.escape_hatch_calls for p in personas)
    total_renders = sum(p.render_calls for p in personas)
    escape_ratio = total_escape / total_renders if total_renders else 0.0
    call_counts = [p.tool_call_count for p in personas]
    latencies = [p.latency_s for p in personas]
    latency_p50 = _percentile(latencies, 0.50)
    latency_p95 = _percentile(latencies, 0.95)
    max_cost = max(p.cost_usd for p in personas)

    return (
        MetricSummary(
            "profile_completeness",
            completeness,
            f">= {PROFILE_COMPLETENESS_THRESHOLD}",
            completeness >= PROFILE_COMPLETENESS_THRESHOLD,
            f"{len(personas)} personas",
        ),
        MetricSummary(
            "precision_at_3",
            precision,
            f">= {PRECISION_AT_3_THRESHOLD}",
            precision >= PRECISION_AT_3_THRESHOLD,
            f"{len(graded)}/{len(feasible)} feasible personas produced a top-3 to grade",
        ),
        MetricSummary(
            "groundedness",
            groundedness,
            f"== {GROUNDEDNESS_THRESHOLD}",
            groundedness >= GROUNDEDNESS_THRESHOLD,
            f"{len(grounded)} personas with a rationale to check",
        ),
        MetricSummary(
            "constraint_compliance",
            float(total_violations),
            "== 0 results violating a stated hard filter/budget/date",
            total_violations == 0,
            f"{total_violations} violation(s) found among the final top-3 results across "
            f"{len(personas)} personas (independently re-checked, not read back from "
            "critic_pass's own verdict)",
        ),
        MetricSummary(
            "guardrail_violations",
            float(total_guardrail),
            "== 0",
            total_guardrail == 0,
            f"{total_guardrail} search-gate denial(s) across {len(personas)} personas",
        ),
        MetricSummary(
            "escape_hatch_ratio",
            escape_ratio,
            f"<= {ESCAPE_HATCH_RATIO_THRESHOLD}",
            escape_ratio <= ESCAPE_HATCH_RATIO_THRESHOLD,
            f"{total_escape} compose_surface call(s) / {total_renders} compiled render(s)",
        ),
        MetricSummary(
            "tool_call_rate",
            sum(call_counts) / len(call_counts),
            f"{TOOL_CALL_RATE_RANGE[0]}-{TOOL_CALL_RATE_RANGE[1]} per session",
            all(TOOL_CALL_RATE_RANGE[0] <= c <= TOOL_CALL_RATE_RANGE[1] for c in call_counts),
            f"min={min(call_counts)}, max={max(call_counts)} audited calls "
            f"across {len(personas)} sessions",
        ),
        MetricSummary(
            "cost_per_session_usd",
            max_cost,
            f"<= {COST_PER_SESSION_THRESHOLD_USD}",
            max_cost <= COST_PER_SESSION_THRESHOLD_USD,
            "DEMO_MODE makes zero model calls (CONSTITUTION III.7); live per-role cost "
            "governance (PHASE-9 SS5) awaits a live rehearsal to price against",
        ),
        MetricSummary(
            "latency_p50_p95_s",
            latency_p95,
            f"p50<={LATENCY_P50_THRESHOLD_S}s, p95<={LATENCY_P95_THRESHOLD_S}s",
            latency_p50 <= LATENCY_P50_THRESHOLD_S and latency_p95 <= LATENCY_P95_THRESHOLD_S,
            f"p50={latency_p50:.3f}s, p95={latency_p95:.3f}s, "
            f"wall-clock over {len(personas)} sessions",
        ),
    )


async def run_eval_harness(
    personas: list[dict[str, Any]], *, store: ListingStore | None = None
) -> EvalReport:
    """Runs every persona through `DEMO_MODE`'s real flow and scores PHASE-9 §4's metrics.
    One shared, seeded store across the whole set (PHASE-1 §4's fixed seed) -- the same
    catalogue every persona is being judged against.
    """
    store = store or InMemoryListingStore.seeded()
    results = tuple([await _eval_one_persona(persona, store) for persona in personas])
    mismatches = tuple(p.name for p in results if p.expect_infeasible != p.reached_infeasible)
    return EvalReport(
        personas=results, metrics=_summarise(results), infeasible_mismatches=mismatches
    )
