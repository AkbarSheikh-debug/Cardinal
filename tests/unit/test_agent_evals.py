"""The eval harness (PHASE-9 §4), exercised at `pytest tests` speed on the 10-persona extra
fixture (gate 9.4/9.5 run the full 30 -- P5's 20-persona golden set plus these) so a
regression in metric computation shows up without waiting on a gate script.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.adapters.store import InMemoryListingStore
from src.agent.evals import (
    ESCAPE_HATCH_RATIO_THRESHOLD,
    PROFILE_COMPLETENESS_THRESHOLD,
    TOOL_CALL_RATE_RANGE,
    _satisfies_profile,
    _violates_constraints,
    run_eval_harness,
)
from src.domain.enums import OfferType, VehicleCategory
from src.domain.money import Money
from src.domain.profile import HardFilter, RequirementProfile
from tests.unit.helpers import make_listing

EXTRA_PERSONAS_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "eval_extra_personas.json"
)


def _extra_personas() -> list[dict[str, object]]:
    return json.loads(EXTRA_PERSONAS_PATH.read_text(encoding="utf-8"))


def _profile(**overrides: object) -> RequirementProfile:
    profile = RequirementProfile()
    if "goal" in overrides:
        profile.goal = profile.goal.fill(overrides["goal"], confidence=0.9, turn=1, locked=True)
    if "category" in overrides:
        profile.category = profile.category.fill(
            overrides["category"], confidence=0.9, turn=1, locked=True
        )
    if "budget" in overrides:
        profile.budget = profile.budget.fill(
            overrides["budget"], confidence=0.9, turn=1, locked=True
        )
    if "target_date" in overrides:
        profile.target_date = profile.target_date.fill(
            overrides["target_date"], confidence=0.9, turn=1, locked=True
        )
    if "hard_filters" in overrides:
        profile.hard_filters = overrides["hard_filters"]  # type: ignore[assignment]
    return profile


def test_extra_personas_fixture_has_ten_entries_covering_every_kind() -> None:
    personas = _extra_personas()
    assert len(personas) == 10
    assert len({p["name"] for p in personas}) == 10
    assert sum(1 for p in personas if p.get("mid_recommend_utterance")) == 3
    assert sum(1 for p in personas if p.get("expect_infeasible")) == 3
    assert sum(1 for p in personas if p.get("decline_at_checkout")) == 2


def test_violates_constraints_catches_an_over_budget_buy_listing() -> None:
    listing = make_listing(price_buy="20000", offer_type=OfferType.BUY)
    profile = _profile(goal=OfferType.BUY, budget=Money.of("15000"))
    assert _violates_constraints(listing, profile)


def test_violates_constraints_ignores_budget_for_a_rent_goal() -> None:
    listing = make_listing(offer_type=OfferType.RENT, price_buy=None)
    profile = _profile(goal=OfferType.RENT, budget=Money.of("100"))
    assert not _violates_constraints(listing, profile)


def test_violates_constraints_catches_a_late_availability_date() -> None:
    listing = make_listing(available_from=date(2026, 11, 1))
    profile = _profile(target_date=date(2026, 9, 15))
    assert _violates_constraints(listing, profile)


def test_violates_constraints_catches_a_generic_hard_filter() -> None:
    listing = make_listing(mileage_km=96000)
    profile = _profile(hard_filters=[HardFilter(field="mileage_km", operator="lte", value=80000)])
    assert _violates_constraints(listing, profile)


def test_violates_constraints_accepts_a_listing_within_every_stated_bound() -> None:
    listing = make_listing(
        price_buy="20000", offer_type=OfferType.BUY, available_from=date(2026, 1, 1)
    )
    profile = _profile(goal=OfferType.BUY, budget=Money.of("25000"), target_date=date(2026, 6, 1))
    assert not _violates_constraints(listing, profile)


def test_satisfies_profile_also_checks_the_requested_category() -> None:
    listing = make_listing(
        category=VehicleCategory.SUV, price_buy="20000", offer_type=OfferType.BUY
    )
    profile = _profile(
        goal=OfferType.BUY, budget=Money.of("25000"), category=[VehicleCategory.SEDAN]
    )
    assert not _satisfies_profile(listing, profile)
    assert not _violates_constraints(listing, profile)  # category mismatch isn't a "violation"


async def test_eval_harness_scores_nine_metrics_on_the_extra_personas() -> None:
    store = InMemoryListingStore.seeded()
    report = await run_eval_harness(_extra_personas(), store=store)

    assert len(report.personas) == 10
    assert len(report.metrics) == 9
    assert {m.name for m in report.metrics} == {
        "profile_completeness",
        "precision_at_3",
        "groundedness",
        "constraint_compliance",
        "guardrail_violations",
        "escape_hatch_ratio",
        "tool_call_rate",
        "cost_per_session_usd",
        "latency_p50_p95_s",
    }
    assert report.all_passed, [m for m in report.metrics if not m.passed]
    # designed to match: the 3 "expect_infeasible" personas should have genuinely produced
    # zero survivors, and nothing else should have -- a mismatch here means either the
    # fixture's tiny budgets stopped being infeasible against the seeded catalogue, or the
    # harness's own infeasibility detection regressed.
    assert report.infeasible_mismatches == ()


async def test_eval_harness_escape_hatch_ratio_is_structurally_zero_in_demo_mode() -> None:
    """`DEMO_MODE` has no model to call `compose_surface` with -- the ratio is 0 by
    construction, not merely below threshold.
    """
    store = InMemoryListingStore.seeded()
    report = await run_eval_harness(_extra_personas(), store=store)
    ratio_metric = report.metric("escape_hatch_ratio")
    assert ratio_metric.value == 0.0
    assert ratio_metric.value <= ESCAPE_HATCH_RATIO_THRESHOLD


async def test_eval_harness_profile_completeness_and_tool_call_rate_are_real_measurements() -> None:
    store = InMemoryListingStore.seeded()
    report = await run_eval_harness(_extra_personas(), store=store)

    completeness = report.metric("profile_completeness")
    assert completeness.value >= PROFILE_COMPLETENESS_THRESHOLD

    for persona in report.personas:
        assert TOOL_CALL_RATE_RANGE[0] <= persona.tool_call_count <= TOOL_CALL_RATE_RANGE[1], (
            f"{persona.name}: {persona.tool_call_count} tool calls outside {TOOL_CALL_RATE_RANGE}"
        )


async def test_decline_at_checkout_personas_reach_an_abandoned_booking() -> None:
    from src.agent.demo import run_demo_session

    store = InMemoryListingStore.seeded()
    persona = next(p for p in _extra_personas() if p.get("decline_at_checkout"))
    result = await run_demo_session(
        list(persona["utterances"]),  # type: ignore[arg-type]
        store=store,
        session_id="test-decline-at-checkout",
        decline_at_checkout=True,
    )
    assert result.state.booking_status == "abandoned"


async def test_zero_result_personas_reach_recommend_with_no_survivors() -> None:
    from src.agent.demo import run_demo_session

    store = InMemoryListingStore.seeded()
    persona = next(p for p in _extra_personas() if p.get("expect_infeasible"))
    result = await run_demo_session(
        list(persona["utterances"]),  # type: ignore[arg-type]
        store=store,
        session_id="test-zero-result",
    )
    assert result.critic_survivors == ()
    assert result.state.infeasible is True
    assert result.state.booking_status is None
