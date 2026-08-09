"""Exports golden A2UI message fixtures from the real Python compiler (`src/mcp/ui/compiler.py`)
into `web/public/fixtures/*.json` (gate 6.2, PHASE-6 SS4/SS7).

These are not hand-typed JSON: gate 6.2's "golden-message fixtures render in a headless
browser with zero console errors" only means something if the fixture is exactly what the
compiler would actually emit for a real tool call, not an approximation of it. Re-run this
after any change to `src/mcp/ui/compiler.py`'s output shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "web" / "public" / "fixtures"


def _write(name: str, messages: list[dict[str, object]]) -> None:
    path = FIXTURES_DIR / name
    path.write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)} ({len(messages)} message(s))")


def main() -> int:
    from src.domain.money import Money
    from src.domain.scoring import CriterionScore, ScoreBreakdown
    from src.domain.tco import TcoComparison, TcoEstimate, TcoLine, TcoLineKind, TcoPath
    from src.mcp.ui.compiler import (
        PowertrainProps,
        compile_detail_surface,
        compile_progress_surface,
        compile_results_surface,
        compile_score_breakdown_surface,
        compile_tco_breakdown_surface,
        compile_tco_surface,
        to_messages,
    )
    from src.mcp.ui.surfaces import SurfaceRegistry
    from src.mcp.ui.validate import validate_component_tree

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    session_id = "golden-fixture-session"

    registry = SurfaceRegistry()
    progress = compile_progress_surface(
        {
            "completed_slots": ["goal", "category"],
            "open_slots": ["budget", "target_date"],
            "reasoning_trace": ["Asked about budget range."],
        },
        phase="interview",
    )
    _write("progress.json", to_messages(session_id, progress, registry))

    registry = SurfaceRegistry()
    # PLAN-02 P13: real listings and their real dealers, so the fixture carries the dealer
    # attribution a live `render_results` would emit rather than a card shape that stopped
    # matching the compiler two phases ago. Gate 13.5 asserts these props render.
    from src.adapters.catalogue.dealers import generate_dealers
    from src.adapters.catalogue.generator import SOURCES, generate_catalogue
    from src.domain.listing import ListingSummary
    from src.mcp.ui.compiler import CardVisual
    from src.mcp.ui.vehicle_models import (
        is_representative,
        vehicle_model_src,
        vehicle_photo_src,
        vehicle_poster_src,
    )

    catalogue = generate_catalogue()
    dealers_by_id = {d.id: d for d in generate_dealers(42, SOURCES)}

    # One from each marketplace, and deliberately one verified dealer *and* one unverified
    # one, so both branches of the card's trust badge live in a golden fixture rather than
    # only in theory -- the same reasoning PHASE-8 §5 gives for deterministic payment
    # failure injection. Gate 13.5 asserts both render.
    def _pick(source: str, *, verified: bool):
        return next(
            x
            for x in catalogue
            if x.source == source
            and x.dealer_id is not None
            and dealers_by_id[x.dealer_id].is_verified is verified
        )

    first = _pick("mock_autobazaar", verified=True)
    second = _pick("mock_drivenow", verified=False)

    def _visual(listing: object) -> CardVisual:
        dealer = dealers_by_id[listing.dealer_id]  # type: ignore[attr-defined]
        return CardVisual(
            headline=ListingSummary.from_listing(listing).headline,  # type: ignore[arg-type]
            model_src=vehicle_model_src(listing.brand, listing.model, listing.category),  # type: ignore[attr-defined]
            poster_src=vehicle_poster_src(listing.brand, listing.model, listing.category),  # type: ignore[attr-defined]
            representative=is_representative(listing.brand, listing.model),  # type: ignore[attr-defined]
            photo_src=vehicle_photo_src(listing.brand, listing.model),  # type: ignore[attr-defined]
            condition=listing.condition.value,  # type: ignore[attr-defined]
            offer_type=listing.offer_type.value,  # type: ignore[attr-defined]
            dealer_name=dealer.display_name,
            dealer_city=dealer.city,
            dealer_rating=float(dealer.rating),
            dealer_verified=dealer.is_verified,
        )

    results = compile_results_surface(
        {
            "weights": {"budget_fit": 0.25, "resale_strength": 0.3},
            "items": [
                {
                    "source": first.source,
                    "source_id": first.source_id,
                    "rank": 1,
                    "score": 0.87,
                    "rationale": "Holds 80% of its value over the pricing horizon.",
                },
                {
                    "source": second.source,
                    "source_id": second.source_id,
                    "rank": 2,
                    "score": 0.79,
                    "rationale": "Priced within the stated budget with low mileage.",
                },
            ],
        },
        visuals={
            (first.source, first.source_id): _visual(first),
            (second.source, second.source_id): _visual(second),
        },
    )
    _write("results.json", to_messages(session_id, results, registry))

    registry = SurfaceRegistry()
    detail = compile_detail_surface(
        {"source": "mock_autobazaar", "source_id": "AB-1073", "show_powertrain_explainer": True},
        headline="2022 Toyota GR86 6MT",
        price_display="EUR 28,500",
        powertrain=PowertrainProps(
            archetype="i4_na",
            model_src="/models/powertrain/i4_na.glb",
            poster_src="/models/powertrain/i4_na.png",
            annotations=(
                {
                    "hotspot": "timing",
                    "label": "Chain",
                    "text": "Chain-driven timing; no belt service.",
                },
            ),
        ),
    )
    _write("detail.json", to_messages(session_id, detail, registry))

    registry = SurfaceRegistry()
    tco = compile_tco_surface(
        {
            "horizon_months": 36,
            "items": [
                {"source": "mock_autobazaar", "source_id": "AB-1073", "total_cost_eur": 32000.0}
            ],
            "break_even_month": 5,
        }
    )
    _write("tco.json", to_messages(session_id, tco, registry))

    registry = SurfaceRegistry()
    comparison = TcoComparison(
        buy=TcoEstimate(
            path=TcoPath.BUY,
            horizon_months=12,
            lines=(TcoLine(kind=TcoLineKind.PURCHASE, amount=Money.of("20000")),),
            total=Money.of("20000"),
        ),
        rent=TcoEstimate(
            path=TcoPath.RENT,
            horizon_months=12,
            lines=(TcoLine(kind=TcoLineKind.RENTAL, amount=Money.of("6000")),),
            total=Money.of("6000"),
        ),
        break_even_month=None,
    )
    tco_breakdown = compile_tco_breakdown_surface(
        comparison, source="mock_autobazaar", source_id="AB-1073"
    )
    _write("tco_breakdown.json", to_messages(session_id, tco_breakdown, registry))

    registry = SurfaceRegistry()
    breakdown = ScoreBreakdown(
        criteria=(
            CriterionScore(
                criterion="budget_fit", weight=0.25, normalised_value=0.9, contribution=0.225
            ),
            CriterionScore(
                criterion="resale_strength", weight=0.3, normalised_value=0.8, contribution=0.24
            ),
        ),
        total=0.465,
    )
    score_breakdown = compile_score_breakdown_surface(
        breakdown, source="mock_autobazaar", source_id="AB-1073"
    )
    _write("score_breakdown.json", to_messages(session_id, score_breakdown, registry))

    # Every fixture must itself be a validated tree -- a golden fixture that the server
    # wouldn't have accepted proves nothing about the renderer (CONSTITUTION II.4).
    for name, compiled in (
        ("progress", progress),
        ("results", results),
        ("detail", detail),
        ("tco", tco),
        ("tco_breakdown", tco_breakdown),
        ("score_breakdown", score_breakdown),
    ):
        errors = validate_component_tree(compiled.components)
        if errors:
            print(f"FIXTURE {name} FAILED VALIDATION: {errors}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    sys.exit(main())
