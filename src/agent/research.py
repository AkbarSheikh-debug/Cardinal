"""Concurrent RESEARCH-phase dispatch (PHASE-3 §4): one researcher per registered
marketplace source, launched together via `asyncio.gather` rather than one after another --
the mechanism gate 3.4 checks for genuinely overlapping timestamps in the trace, as opposed
to two sequential calls that would look identical in the final output and completely
different in the trace (PHASE-3 §4's own framing of why this matters).

In a live session this is what the orchestrator's two `researcher` subagent launches do at
the Claude Agent SDK level; this module is the same fan-out over the real `ListingStore`,
used directly by `DEMO_MODE` so the demo's candidates are real query results, not fixtures.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from src.adapters.registry import registered_source_names
from src.adapters.store import ListingStore
from src.agent.tracing import subagent_span
from src.domain.dates import DateRange
from src.domain.enums import OfferType, VehicleCategory
from src.domain.marketplace import SearchQuery
from src.domain.profile import RequirementProfile


@dataclass(frozen=True)
class ResearchTrace:
    source: str
    started_at: float
    finished_at: float
    candidate_ids: tuple[str, ...]


def _query_from_profile(profile: RequirementProfile) -> SearchQuery:
    kwargs: dict[str, object] = {}
    if profile.category.is_filled:
        categories: list[VehicleCategory] = profile.category.value or []
        kwargs["categories"] = tuple(categories)
    if profile.goal.is_filled:
        kwargs["offer_type"] = profile.goal.value
    # `budget` is one slot for both a purchase price and a rental total -- `SearchQuery`
    # only has a *purchase*-price filter (`max_price`), so applying it to a rent-only
    # profile would filter every rentable listing on its unrelated `price_buy`, which is
    # `None` for the 90 rent-only rows and excludes them outright. P3 has no distinct
    # `max_rental_daily` slot to fill instead (P4/P5's problem); until it does, a rental
    # goal skips the price filter rather than applying the wrong one.
    if profile.budget.is_filled and profile.goal.value != OfferType.RENT:
        kwargs["max_price"] = profile.budget.value
    if profile.target_date.is_filled:
        # `available_between` only ever checks its `.end` (D-008) -- a degenerate one-day
        # range is enough to mean "becomes available on or before the target date." Without
        # this, RESEARCH could hand RECOMMEND a candidate that isn't even ready in time,
        # which is exactly the seeded violation P5's critic pass exists to catch (gate 5.8) --
        # catching it here means it never has to (DECISIONS.md D-020).
        kwargs["available_between"] = DateRange(
            start=profile.target_date.value, end=profile.target_date.value
        )
    return SearchQuery(**kwargs)


async def _research_one_source(
    store: ListingStore, source: str, query: SearchQuery, *, simulated_latency_s: float
) -> ResearchTrace:
    # Gate 9.3: opened while `dispatch_researchers`' `asyncio.gather` call is itself inside
    # the RESEARCH phase span's context -- each task snapshots that as its parent when
    # `gather` schedules it, so these come out as genuine sibling spans in the real trace,
    # not just entries in `ResearchTrace.started_at`/`finished_at` that merely claim overlap.
    with subagent_span(source) as span:
        started = time.monotonic()
        if simulated_latency_s:
            # A real marketplace call takes tens to hundreds of milliseconds; the in-memory
            # demo store answers in microseconds, which would make two `asyncio.gather`-launched
            # tasks complete inside a single event-loop tick with no *observable* overlap even
            # though they were genuinely scheduled together. This sleep is what makes the
            # overlap gate 3.4 checks for a real, stable measurement rather than a coin flip.
            await asyncio.sleep(simulated_latency_s)
        listings, _total = await store.query(query, sources=(source,))
        finished = time.monotonic()
        span.set_attribute("researcher.candidate_count", len(listings))
        return ResearchTrace(
            source=source,
            started_at=started,
            finished_at=finished,
            candidate_ids=tuple(f"{listing.source}:{listing.source_id}" for listing in listings),
        )


async def dispatch_researchers(
    store: ListingStore, profile: RequirementProfile, *, simulated_latency_s: float = 0.0
) -> tuple[ResearchTrace, ...]:
    query = _query_from_profile(profile)
    sources = registered_source_names()
    results = await asyncio.gather(
        *(
            _research_one_source(store, source, query, simulated_latency_s=simulated_latency_s)
            for source in sources
        )
    )
    return tuple(results)


def traces_overlap(traces: tuple[ResearchTrace, ...]) -> bool:
    """True when at least two traces were genuinely in flight at the same time."""
    for i, a in enumerate(traces):
        for b in traces[i + 1 :]:
            if a.started_at < b.finished_at and b.started_at < a.finished_at:
                return True
    return False
