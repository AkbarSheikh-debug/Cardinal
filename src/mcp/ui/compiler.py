"""The compiler (PHASE-6 SS4): semantic tool call -> A2UI component tree. Deterministic,
pure functions of their inputs -- "compile_results_surface(args)  # pure function,
unit-tested" is PHASE-6 SS4's own worked example, and every function below holds to it: no
I/O, no clock, no randomness. Whatever enrichment a handler needs beyond a tool's own frozen
P2 schema (a `Listing`'s headline, a resolved GLB path) is fetched by the caller in
`src/mcp/ui/tools.py` and passed in as plain primitives, the same seam D-020 already used to
keep `src/domain/scoring.py` pure while `src/domain/ranking.py` does the I/O-adjacent work.

Four semantic compilers, one per `render_*` tool, plus two "no recomputation" compilers that
map a real P5 object (`ScoreBreakdown`, `TcoComparison`) straight into props -- these are what
back the "expanded card" / itemised-TCO paths PHASE-6 SS3's table describes, reached by a
user action rather than a fresh model tool call (PHASE-6 SS6's action round-trip), so the
number on screen is never a second computation of a number P5 already produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domain.scoring import ScoreBreakdown
from src.domain.tco import TcoComparison
from src.mcp.ui.catalog import CATALOG_ID
from src.mcp.ui.messages import (
    ComponentDict,
    Message,
    component,
    create_surface_message,
    update_components_message,
    update_data_model_message,
)
from src.mcp.ui.surfaces import SurfaceKind, SurfaceRegistry

ROOT_ID = "root"


@dataclass(frozen=True)
class CompiledSurface:
    kind: SurfaceKind
    components: list[ComponentDict]
    data_model: dict[str, Any] | None = None


@dataclass(frozen=True)
class PowertrainProps:
    archetype: str
    model_src: str
    poster_src: str
    annotations: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class CardVisual:
    """Per-card enrichment `render_results`' frozen P2 schema does not carry (D-060).

    Resolved by the handler in `src/mcp/ui/tools.py` from the real `Listing` and passed in as
    primitives, the same seam this module's docstring already describes for `render_detail`'s
    headline -- the compiler never touches a store, a clock, or a filesystem.
    """

    headline: str
    model_src: str
    poster_src: str
    #: True when `model_src` is a body-style silhouette rather than a model of this actual
    #: car, so the card can say which of the two it is showing.
    representative: bool


# -- render_progress ----------------------------------------------------------------------------


def compile_progress_surface(args: dict[str, Any], *, phase: str) -> CompiledSurface:
    """`phase` is not in `render_progress`'s frozen P2 schema (it only carries
    `completed_slots`/`open_slots`/`reasoning_trace`) -- the handler reads it off the session's
    own `SessionState` and passes it in, rather than the compiler inventing or guessing it.
    """
    slots = [{"name": name, "status": "filled"} for name in args.get("completed_slots", [])]
    slots += [{"name": name, "status": "open"} for name in args.get("open_slots", [])]
    props: dict[str, Any] = {"slots": slots, "phase": phase}
    trace = args.get("reasoning_trace")
    if trace:
        props["reasoningTrace"] = list(trace)
    return CompiledSurface(
        kind=SurfaceKind.PROGRESS,
        components=[component(ROOT_ID, "InterviewProgress", props)],
    )


# -- render_results -------------------------------------------------------------------------------


def compile_results_surface(
    args: dict[str, Any],
    *,
    visuals: dict[tuple[str, str], CardVisual] | None = None,
) -> CompiledSurface:
    """One `CarCard` per item, in a `Column` -- the flat list-of-components-plus-id-refs shape
    `updateComponents` requires (`common_types.json#/$defs/ChildList`), not inline nesting.

    `visuals` keys off `(source, source_id)` and is optional throughout: an item with no entry
    compiles to exactly the card it compiled to before D-060, so a caller with no store wired
    up (or a listing that has since been withdrawn) degrades to a text card rather than to an
    error or a broken `<model-viewer>`.
    """
    items = args.get("items", [])
    card_ids = [f"card-{i}" for i in range(len(items))]
    cards = []
    for i, item in enumerate(items):
        props: dict[str, Any] = {
            "source": item["source"],
            "sourceId": item["source_id"],
            "rank": item["rank"],
            "score": item["score"],
            "rationale": item["rationale"],
        }
        visual = (visuals or {}).get((item["source"], item["source_id"]))
        if visual is not None:
            props["headline"] = visual.headline
            props["modelSrc"] = visual.model_src
            props["posterSrc"] = visual.poster_src
            props["representative"] = visual.representative
        cards.append(component(card_ids[i], "CarCard", props))
    root = component(ROOT_ID, "Column", {"children": card_ids})
    return CompiledSurface(kind=SurfaceKind.RESULTS, components=[root, *cards])


# -- render_detail --------------------------------------------------------------------------------


def compile_detail_surface(
    args: dict[str, Any],
    *,
    headline: str,
    price_display: str,
    powertrain: PowertrainProps | None = None,
) -> CompiledSurface:
    body_ids = ["detail-headline", "detail-price"]
    parts = [
        component("detail-headline", "Text", {"text": headline, "variant": "h3"}),
        component("detail-price", "Text", {"text": price_display}),
    ]
    if args.get("show_powertrain_explainer") and powertrain is not None:
        body_ids.append("detail-powertrain")
        parts.append(
            component(
                "detail-powertrain",
                "PowertrainExplainer",
                {
                    "archetype": powertrain.archetype,
                    "modelSrc": powertrain.model_src,
                    "posterSrc": powertrain.poster_src,
                    "annotations": list(powertrain.annotations),
                },
            )
        )
    body = component("detail-body", "Column", {"children": body_ids})
    root = component(ROOT_ID, "Card", {"child": "detail-body"})
    return CompiledSurface(kind=SurfaceKind.DETAIL, components=[root, body, *parts])


# -- render_tco -----------------------------------------------------------------------------------


def compile_tco_surface(args: dict[str, Any]) -> CompiledSurface:
    """The summary form: whatever `render_tco`'s frozen schema was actually called with (a
    total per listing over the stated horizon). `compile_tco_breakdown_surface` below is the
    itemised, "no recomputation" counterpart for when a real `TcoComparison` is on hand.
    """
    series = [
        {
            "source": item["source"],
            "sourceId": item["source_id"],
            "totalCostEur": item["total_cost_eur"],
        }
        for item in args.get("items", [])
    ]
    props: dict[str, Any] = {"series": series}
    if "break_even_month" in args and args["break_even_month"] is not None:
        props["breakEvenMonth"] = args["break_even_month"]
    return CompiledSurface(kind=SurfaceKind.TCO, components=[component(ROOT_ID, "TcoChart", props)])


def compile_tco_breakdown_surface(
    comparison: TcoComparison, *, source: str, source_id: str
) -> CompiledSurface:
    """Maps a real `TcoComparison` (`src/domain/tco.py`) straight into `TcoChart` props --
    every line item and the break-even month exactly as P5's engine computed them.
    """

    def _path(estimate: Any) -> dict[str, Any]:
        return {
            "path": estimate.path.value,
            "total": float(estimate.total.amount),
            "lines": [
                {
                    "kind": line.kind.value,
                    "amountEur": float(line.amount.amount),
                    "note": line.note,
                }
                for line in estimate.lines
            ],
        }

    props: dict[str, Any] = {
        "series": [
            {"source": source, "sourceId": source_id, **_path(comparison.buy)},
            {"source": source, "sourceId": source_id, **_path(comparison.rent)},
        ]
    }
    if comparison.break_even_month is not None:
        props["breakEvenMonth"] = comparison.break_even_month
    return CompiledSurface(kind=SurfaceKind.TCO, components=[component(ROOT_ID, "TcoChart", props)])


def compile_score_breakdown_surface(
    breakdown: ScoreBreakdown, *, source: str, source_id: str
) -> CompiledSurface:
    """Maps a real `ScoreBreakdown` (`src/domain/scoring.py`) straight into `ScoreBreakdown`
    props -- PHASE-6 SS3's own worked registration example, field for field: `criteria[].name`
    /`weight`/`value`/`contribution`. The stacked bar the client renders from this can never
    disagree with the ranking, because it is the ranking.
    """
    props = {
        "source": source,
        "sourceId": source_id,
        "criteria": [
            {
                "name": c.criterion,
                "weight": c.weight,
                "value": c.normalised_value,
                "contribution": c.contribution,
            }
            for c in breakdown.criteria
        ],
    }
    return CompiledSurface(
        kind=SurfaceKind.SCORE_BREAKDOWN, components=[component(ROOT_ID, "ScoreBreakdown", props)]
    )


# -- surface identity + emission (PHASE-6 SS6, gate 6.6) -------------------------------------------


def to_messages(
    session_id: str, compiled: CompiledSurface, registry: SurfaceRegistry
) -> list[Message]:
    """`createSurface` only on the *first* time this `(session_id, kind)` pair is compiled --
    every later call for the same pair is `updateComponents` (+ `updateDataModel` if the
    compiled surface carries a data model), never a second `createSurface`. This is the whole
    mechanism gate 6.6 asserts: surface identity is a property of `SurfaceRegistry`, not of
    whether the compiler happened to be called again.
    """
    surface_id, needs_create = registry.ensure_created(session_id, compiled.kind)
    messages: list[Message] = []
    if needs_create:
        messages.append(create_surface_message(surface_id, catalog_id=CATALOG_ID))
    messages.append(update_components_message(surface_id, compiled.components))
    if compiled.data_model is not None:
        messages.append(update_data_model_message(surface_id, compiled.data_model))
    return messages
