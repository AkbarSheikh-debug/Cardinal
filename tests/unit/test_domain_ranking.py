"""The ranking engine (PHASE-5 §3-§4, §6, §8, §9): hard filters, deterministic ranking,
grounding, and the critic pass. `src/domain/ranking.py` is the seam that reads `Listing` and
`RequirementProfile`; `tests/unit/test_domain_scoring.py` covers the pure math it calls into.
"""

from __future__ import annotations

from datetime import date

from src.domain.enums import OfferType, VehicleCategory
from src.domain.money import Money
from src.domain.profile import HardFilter, RequirementProfile
from src.domain.ranking import (
    apply_hard_filters,
    build_rationale,
    critic_pass,
    finalize_rationale,
    rank,
    score_listing,
    validate_grounding,
)
from src.domain.scoring import DEFAULT_WEIGHTS, FieldRef, RankedResult
from tests.unit.helpers import make_listing


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
        profile.hard_filters = overrides["hard_filters"]
    return profile


# -- hard filters (gate 5.3) --------------------------------------------------------------------


def test_apply_hard_filters_removes_rows_that_fail() -> None:
    low_mileage = make_listing(source_id="LOW", mileage_km=20000)
    high_mileage = make_listing(source_id="HIGH", mileage_km=90000)
    filters = [HardFilter(field="mileage_km", operator="lte", value=80000)]
    survivors = apply_hard_filters([low_mileage, high_mileage], filters)
    assert [listing.source_id for listing in survivors] == ["LOW"]


def test_apply_hard_filters_no_filters_is_a_no_op() -> None:
    listings = [make_listing(source_id="A"), make_listing(source_id="B")]
    assert apply_hard_filters(listings, []) == listings


def test_hard_filtered_listing_never_appears_at_any_rank() -> None:
    low_mileage = make_listing(source_id="LOW", mileage_km=20000)
    high_mileage = make_listing(source_id="HIGH", mileage_km=90000)
    profile = _profile(hard_filters=[HardFilter(field="mileage_km", operator="lte", value=80000)])
    result = rank([low_mileage, high_mileage], profile)
    surviving_ids = {r.listing_id for r in result.ranked}
    assert high_mileage.id not in surviving_ids
    assert low_mileage.id in surviving_ids


# -- determinism (gate 5.1) ----------------------------------------------------------------------


def test_rank_is_deterministic_across_two_runs() -> None:
    listings = [
        make_listing(
            source_id=f"L{i}", mileage_km=10000 + i * 5000, price_buy=str(15000 + i * 1000)
        )
        for i in range(8)
    ]
    profile = _profile(
        goal=OfferType.BUY,
        category=[VehicleCategory.SEDAN],
        budget=Money.of("25000"),
        target_date=date(2026, 6, 1),
    )
    for listing in listings:
        listing.category = VehicleCategory.SEDAN
        listing.available_from = date(2026, 3, 1)

    first = rank(listings, profile)
    second = rank(listings, profile)
    assert [r.model_dump_json() for r in first.ranked] == [
        r.model_dump_json() for r in second.ranked
    ]


def test_rank_sorts_by_score_desc_then_listing_id_asc_on_ties() -> None:
    # Two identical listings (aside from id) must score identically and tie-break on id.
    a = make_listing(source_id="AAA")
    b = make_listing(source_id="BBB")
    profile = _profile()
    result = rank([b, a], profile)
    assert len(result.ranked) == 2
    assert result.ranked[0].breakdown.total == result.ranked[1].breakdown.total
    ordered_ids = [r.listing_id for r in result.ranked]
    assert ordered_ids == sorted(ordered_ids, key=str)


def test_rank_of_empty_candidates_is_empty() -> None:
    result = rank([], _profile())
    assert result.ranked == ()


# -- score_breakdown / ScoreBreakdown invariant (gate 5.2) ----------------------------------------


def test_score_listing_breakdown_sums_correctly() -> None:
    listing = make_listing()
    breakdown = score_listing(listing, _profile(), DEFAULT_WEIGHTS, running_cost_population=[100.0])
    assert abs(breakdown.total - sum(c.contribution for c in breakdown.criteria)) < 1e-9


# -- grounding (gate 5.5, CONSTITUTION II.3) -------------------------------------------------------


def test_build_rationale_is_always_grounded() -> None:
    listing = make_listing()
    profile = _profile(budget=Money.of("25000"))
    breakdown = score_listing(listing, profile, DEFAULT_WEIGHTS, running_cost_population=[100.0])
    text, citations = build_rationale(listing, breakdown, profile)
    listings_by_key = {f"{listing.source}:{listing.source_id}": listing}
    ok, ungrounded = validate_grounding(text, citations, listings_by_key)
    assert ok, f"unexpected ungrounded numbers: {ungrounded}"


def test_validate_grounding_rejects_a_fabricated_statistic() -> None:
    listing = make_listing()
    listing_key = f"{listing.source}:{listing.source_id}"
    listings_by_key = {listing_key: listing}
    citations = (FieldRef(listing_id=listing_key, field_name="depreciation_curve"),)
    fabricated = "Retains an implausible 999% of its value, unlike anything in the curve."
    ok, ungrounded = validate_grounding(fabricated, citations, listings_by_key)
    assert not ok
    assert 999.0 in ungrounded


def test_validate_grounding_ignores_uncited_listings() -> None:
    text = "Priced at EUR 20,000."
    ok, ungrounded = validate_grounding(text, (), {})
    assert not ok
    assert 20000.0 in ungrounded


def test_finalize_rationale_returns_the_first_grounded_candidate() -> None:
    listing = make_listing()
    listings_by_key = {f"{listing.source}:{listing.source_id}": listing}
    good_text = f"{listing.mileage_km:,} km on the odometer."
    good_citations = (
        FieldRef(listing_id=f"{listing.source}:{listing.source_id}", field_name="mileage_km"),
    )
    text, citations, grounded = finalize_rationale([(good_text, good_citations)], listings_by_key)
    assert grounded
    assert text == good_text
    assert citations == good_citations


def test_finalize_rationale_degrades_to_unverified_after_exhausting_retries() -> None:
    bad_text = "Retains 999% of its value."
    text, citations, grounded = finalize_rationale([(bad_text, ()), (bad_text, ())], {})
    assert not grounded
    assert citations == ()
    assert text.startswith("[unverified]")


# -- critic pass (gate 5.8) ------------------------------------------------------------------------


def test_critic_pass_catches_a_listing_available_after_the_target_date() -> None:
    late_listing = make_listing(source_id="LATE", available_from=date(2026, 10, 1))
    on_time_listing = make_listing(source_id="ONTIME", available_from=date(2026, 1, 1))
    profile = _profile(target_date=date(2026, 3, 1))

    ranking_result = rank([late_listing, on_time_listing], profile)
    listings_by_id = {late_listing.id: late_listing, on_time_listing.id: on_time_listing}
    survivors, violations = critic_pass(ranking_result.ranked, listings_by_id, profile)

    surviving_ids = {r.listing_id for r in survivors}
    assert late_listing.id not in surviving_ids
    assert on_time_listing.id in surviving_ids
    assert any("available_from" in v and "target_date" in v for v in violations)


def test_critic_pass_renumbers_ranks_after_dropping_a_violator() -> None:
    late_listing = make_listing(source_id="LATE", available_from=date(2026, 10, 1))
    on_time_listing = make_listing(source_id="ONTIME", available_from=date(2026, 1, 1))
    profile = _profile(target_date=date(2026, 3, 1))
    ranking_result = rank([late_listing, on_time_listing], profile)
    listings_by_id = {late_listing.id: late_listing, on_time_listing.id: on_time_listing}
    survivors, _violations = critic_pass(ranking_result.ranked, listings_by_id, profile)
    assert [r.rank for r in survivors] == list(range(1, len(survivors) + 1))


def test_critic_pass_catches_over_budget_price() -> None:
    over_budget = make_listing(source_id="OVER", price_buy="50000", market_value="50000")
    within_budget = make_listing(source_id="WITHIN", price_buy="15000", market_value="15000")
    profile = _profile(goal=OfferType.BUY, budget=Money.of("20000"))
    ranking_result = rank([over_budget, within_budget], profile)
    listings_by_id = {over_budget.id: over_budget, within_budget.id: within_budget}
    survivors, violations = critic_pass(ranking_result.ranked, listings_by_id, profile)
    surviving_ids = {r.listing_id for r in survivors}
    assert over_budget.id not in surviving_ids
    assert within_budget.id in surviving_ids
    assert any("exceeds budget" in v for v in violations)


def test_critic_pass_passes_clean_candidates_through_untouched() -> None:
    listing = make_listing()
    profile = _profile()
    ranking_result = rank([listing], profile)
    survivors, violations = critic_pass(ranking_result.ranked, {listing.id: listing}, profile)
    assert violations == ()
    assert len(survivors) == 1
    assert isinstance(survivors[0], RankedResult)
