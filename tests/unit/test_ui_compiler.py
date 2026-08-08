"""The compiler (PHASE-6 SS4) and surface-identity emission (SS6, gate 6.6), tested directly
-- pure functions, no MCP server or transport involved. `tests/unit/test_mcp_ui.py` covers the
same behaviour through the real tool call path; this file is what a future refactor of the
compiler itself should be checked against first.
"""

from __future__ import annotations

from src.domain.money import Money
from src.domain.scoring import CriterionScore, ScoreBreakdown
from src.domain.tco import TcoComparison, TcoEstimate, TcoLine, TcoLineKind, TcoPath
from src.mcp.ui.compiler import (
    compile_progress_surface,
    compile_results_surface,
    compile_score_breakdown_surface,
    compile_tco_breakdown_surface,
    compile_tco_surface,
    to_messages,
)
from src.mcp.ui.surfaces import SurfaceRegistry
from src.mcp.ui.validate import validate_component_tree


def test_compile_progress_surface_maps_slots_and_carries_phase() -> None:
    compiled = compile_progress_surface(
        {"completed_slots": ["goal"], "open_slots": ["budget", "category"]}, phase="research"
    )
    root = compiled.components[0]
    assert root["component"] == "InterviewProgress"
    assert root["phase"] == "research"
    assert {"name": "goal", "status": "filled"} in root["slots"]
    assert {"name": "budget", "status": "open"} in root["slots"]
    assert validate_component_tree(compiled.components) == []


def test_compile_results_surface_produces_a_valid_tree() -> None:
    args = {
        "weights": {"budget_fit": 1.0},
        "items": [
            {
                "source": "mock_autobazaar",
                "source_id": "AB-1",
                "rank": 1,
                "score": 0.9,
                "rationale": "cheapest",
            }
        ],
    }
    compiled = compile_results_surface(args)
    assert validate_component_tree(compiled.components) == []
    card = next(c for c in compiled.components if c["component"] == "CarCard")
    assert card["sourceId"] == "AB-1"


def test_compile_tco_surface_is_a_valid_tree() -> None:
    args = {
        "horizon_months": 12,
        "items": [{"source": "mock_autobazaar", "source_id": "AB-1", "total_cost_eur": 1000.0}],
        "break_even_month": 5,
    }
    compiled = compile_tco_surface(args)
    assert validate_component_tree(compiled.components) == []
    root = compiled.components[0]
    assert root["breakEvenMonth"] == 5


def _fixture_comparison() -> TcoComparison:
    buy = TcoEstimate(
        path=TcoPath.BUY,
        horizon_months=12,
        lines=(TcoLine(kind=TcoLineKind.PURCHASE, amount=Money.of("10000")),),
        total=Money.of("10000"),
    )
    rent = TcoEstimate(
        path=TcoPath.RENT,
        horizon_months=12,
        lines=(TcoLine(kind=TcoLineKind.RENTAL, amount=Money.of("6000")),),
        total=Money.of("6000"),
    )
    return TcoComparison(buy=buy, rent=rent, break_even_month=None)


def test_compile_tco_breakdown_surface_renders_the_real_comparison_no_recomputation() -> None:
    comparison = _fixture_comparison()
    compiled = compile_tco_breakdown_surface(comparison, source="mock_autobazaar", source_id="AB-1")
    assert validate_component_tree(compiled.components) == []
    root = compiled.components[0]
    totals = {entry["path"]: entry["total"] for entry in root["series"]}
    assert totals["buy"] == 10000.0
    assert totals["rent"] == 6000.0
    assert "breakEvenMonth" not in root  # None means never crosses -- honestly omitted


def test_compile_score_breakdown_surface_maps_every_criterion() -> None:
    breakdown = ScoreBreakdown(
        criteria=(
            CriterionScore(
                criterion="budget_fit", weight=0.6, normalised_value=0.5, contribution=0.3
            ),
            CriterionScore(
                criterion="resale_strength", weight=0.4, normalised_value=1.0, contribution=0.4
            ),
        ),
        total=0.7,
    )
    compiled = compile_score_breakdown_surface(
        breakdown, source="mock_autobazaar", source_id="AB-1"
    )
    assert validate_component_tree(compiled.components) == []
    root = compiled.components[0]
    assert root["component"] == "ScoreBreakdown"
    names = {c["name"] for c in root["criteria"]}
    assert names == {"budget_fit", "resale_strength"}
    contributions = {c["name"]: c["contribution"] for c in root["criteria"]}
    assert contributions["resale_strength"] == 0.4


def test_to_messages_creates_once_then_only_updates() -> None:
    registry = SurfaceRegistry()
    session_id = "sess-1"
    first = compile_results_surface(
        {
            "weights": {"a": 1.0},
            "items": [{"source": "s", "source_id": "1", "rank": 1, "score": 0.9, "rationale": "r"}],
        }
    )
    messages_1 = to_messages(session_id, first, registry)
    assert any("createSurface" in m for m in messages_1)

    second = compile_results_surface(
        {
            "weights": {"a": 1.0},
            "items": [
                {"source": "s", "source_id": "1", "rank": 1, "score": 0.95, "rationale": "updated"}
            ],
        }
    )
    messages_2 = to_messages(session_id, second, registry)
    assert not any("createSurface" in m for m in messages_2)
    assert all("updateComponents" in m or "updateDataModel" in m for m in messages_2)

    surface_ids = {m["createSurface"]["surfaceId"] for m in messages_1 if "createSurface" in m}
    surface_ids |= {
        m["updateComponents"]["surfaceId"] for m in messages_2 if "updateComponents" in m
    }
    assert len(surface_ids) == 1, "the second call must target the same surface id"


def test_different_surface_kinds_get_different_ids_in_the_same_session() -> None:
    registry = SurfaceRegistry()
    progress = to_messages(
        "sess-1",
        compile_progress_surface({"completed_slots": [], "open_slots": []}, phase="interview"),
        registry,
    )
    results = to_messages(
        "sess-1",
        compile_results_surface(
            {
                "weights": {},
                "items": [
                    {"source": "s", "source_id": "1", "rank": 1, "score": 1.0, "rationale": "r"}
                ],
            }
        ),
        registry,
    )
    progress_id = progress[0]["createSurface"]["surfaceId"]
    results_id = results[0]["createSurface"]["surfaceId"]
    assert progress_id != results_id
