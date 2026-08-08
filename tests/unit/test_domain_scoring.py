"""Pure scoring math (PHASE-5 §4, §9). No `Listing`, no fixtures, no event loop needed --
these are property tests of primitives, which is the entire point of keeping
`src/domain/scoring.py` stdlib+pydantic only (gate 5.9).
"""

from __future__ import annotations

import math

from src.domain.scoring import (
    DEFAULT_WEIGHTS,
    Criterion,
    CriterionWeight,
    WeightSet,
    extract_numbers,
    normalise_availability,
    normalise_budget_fit,
    normalise_category_match,
    normalise_resale_strength,
    normalise_running_cost,
    ranking_sort_key,
    score_breakdown,
    zscore,
)


def test_default_weights_are_normalised_to_one() -> None:
    assert math.isclose(sum(w.weight for w in DEFAULT_WEIGHTS.weights), 1.0, abs_tol=1e-9)


def test_default_weights_cover_exactly_the_five_mvp_criteria() -> None:
    names = {w.criterion for w in DEFAULT_WEIGHTS.weights}
    assert names == {c.value for c in Criterion}


# -- budget_fit ---------------------------------------------------------------------------------


def test_budget_fit_full_marks_at_or_below_80_percent() -> None:
    assert normalise_budget_fit(8000, 10000) == 1.0
    assert normalise_budget_fit(1000, 10000) == 1.0


def test_budget_fit_decays_linearly_between_threshold_and_ceiling() -> None:
    # Halfway between 80% (8000) and 100% (10000) of a 10000 ceiling.
    assert math.isclose(normalise_budget_fit(9000, 10000), 0.5, abs_tol=1e-9)


def test_budget_fit_is_a_hard_zero_above_the_ceiling() -> None:
    assert normalise_budget_fit(10000.01, 10000) == 0.0
    assert normalise_budget_fit(50000, 10000) == 0.0


def test_budget_fit_rejects_a_non_positive_ceiling() -> None:
    import pytest

    with pytest.raises(ValueError, match="positive"):
        normalise_budget_fit(100, 0)


# -- resale_strength ------------------------------------------------------------------------------


def test_resale_strength_clamps_into_zero_one() -> None:
    assert normalise_resale_strength(0.55) == 0.55
    assert normalise_resale_strength(1.4) == 1.0
    assert normalise_resale_strength(-0.2) == 0.0


# -- category_match -------------------------------------------------------------------------------


def test_category_match_no_stated_preference_is_not_a_mismatch() -> None:
    assert normalise_category_match("suv", [], locked=False, confidence=0.0) == 1.0


def test_category_match_explicit_beats_inferred() -> None:
    explicit = normalise_category_match("suv", ["suv"], locked=True, confidence=0.5)
    inferred = normalise_category_match("suv", ["suv"], locked=False, confidence=0.6)
    assert explicit == 1.0
    assert inferred == 0.6
    assert explicit > inferred


def test_category_match_miss_scores_zero() -> None:
    assert normalise_category_match("sedan", ["suv"], locked=True, confidence=1.0) == 0.0


def test_category_match_inferred_has_a_floor() -> None:
    assert normalise_category_match("suv", ["suv"], locked=False, confidence=0.1) == 0.5


# -- availability ---------------------------------------------------------------------------------


def test_availability_negative_gap_is_a_hard_zero() -> None:
    assert normalise_availability(-1) == 0.0
    assert normalise_availability(-100) == 0.0


def test_availability_decays_up_to_the_buffer_then_caps_at_one() -> None:
    assert normalise_availability(0) == 0.0
    assert normalise_availability(7, buffer_days=14) == 0.5
    assert normalise_availability(14, buffer_days=14) == 1.0
    assert normalise_availability(30, buffer_days=14) == 1.0


# -- running_cost / zscore ------------------------------------------------------------------------


def test_zscore_of_too_small_a_population_is_zero() -> None:
    assert zscore(100.0, [100.0]) == 0.0
    assert zscore(100.0, []) == 0.0


def test_zscore_zero_spread_population_is_zero() -> None:
    assert zscore(50.0, [50.0, 50.0, 50.0]) == 0.0


def test_running_cost_lower_is_better() -> None:
    population = [100.0, 200.0, 300.0]
    cheap = normalise_running_cost(100.0, population)
    expensive = normalise_running_cost(300.0, population)
    assert cheap > expensive


def test_running_cost_clamped_into_zero_one_for_extreme_outliers() -> None:
    population = [100.0] * 20 + [10000.0]
    assert 0.0 <= normalise_running_cost(10000.0, population) <= 1.0
    assert 0.0 <= normalise_running_cost(1.0, population) <= 1.0


# -- score_breakdown / sort key --------------------------------------------------------------------


def test_score_breakdown_contributions_sum_to_total_within_tolerance() -> None:
    weights = WeightSet(
        weights=(
            CriterionWeight(criterion="a", weight=0.6),
            CriterionWeight(criterion="b", weight=0.4),
        )
    )
    breakdown = score_breakdown(weights, {"a": 0.5, "b": 1.0})
    contributed = sum(c.contribution for c in breakdown.criteria)
    assert math.isclose(breakdown.total, contributed, abs_tol=1e-9)
    assert math.isclose(breakdown.total, 0.6 * 0.5 + 0.4 * 1.0, abs_tol=1e-9)


def test_score_breakdown_raises_on_a_missing_criterion() -> None:
    import pytest

    weights = WeightSet(weights=(CriterionWeight(criterion="a", weight=1.0),))
    with pytest.raises(KeyError):
        score_breakdown(weights, {})


def test_ranking_sort_key_orders_by_score_desc_then_id_asc() -> None:
    keys = sorted(
        [ranking_sort_key(0.5, "b"), ranking_sort_key(0.9, "a"), ranking_sort_key(0.5, "a")]
    )
    # Highest score first...
    assert keys[0] == ranking_sort_key(0.9, "a")
    # ...ties broken on id, ascending.
    assert keys[1] == ranking_sort_key(0.5, "a")
    assert keys[2] == ranking_sort_key(0.5, "b")


# -- grounding: number extraction ------------------------------------------------------------------


def test_extract_numbers_strips_thousands_separators() -> None:
    assert extract_numbers("Priced at EUR 21,899 with 62,450 km") == (21899.0, 62450.0)


def test_extract_numbers_handles_percentages_and_decimals() -> None:
    assert extract_numbers("Retains 83% of its value, EUR 1234.56 total") == (83.0, 1234.56)


def test_extract_numbers_empty_for_numberless_text() -> None:
    assert extract_numbers("no digits here at all") == ()
