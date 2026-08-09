"""`src/domain/lead_scoring.py` -- PLAN-02 P15.

Pure functions of primitives, so every test here runs with no store, no clock and no event
loop -- the same bar `test_domain_scoring.py` holds P5's scorer to (gate 5.9).

The file is organised around the four properties the gate asserts: determinism (15.2), the
contributions summing to the score (15.3), the tier thresholds landing where PLAN-02 §P15's
table says they should, and income being structurally incapable of affecting anything (15.9).
"""

from __future__ import annotations

import inspect
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.domain import lead_scoring
from src.domain.lead import IntentTier, LeadEvent
from src.domain.lead_scoring import (
    HIGH_THRESHOLD,
    MEDIUM_THRESHOLD,
    WEIGHTS,
    normalise_budget_fit,
    normalise_return_sessions,
    normalise_target_date,
    score_lead,
    tier_for,
)

TODAY = date(2026, 8, 9)
CART = (LeadEvent.CART_ADD,)
CART_AND_CHECKOUT = (LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED)
EVERYTHING = (LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED, LeadEvent.BOOKING_SUBMITTED)


def score(**overrides: object):
    kwargs: dict[str, object] = {
        "events": CART,
        "target_date": None,
        "today": TODAY,
        "budget": None,
        "price": None,
    }
    kwargs.update(overrides)
    return score_lead(**kwargs)  # type: ignore[arg-type]


# -- the weights ---------------------------------------------------------------------


def test_weights_sum_to_one() -> None:
    """Asserted at import too, so a bad edit fails on the way in rather than here -- this
    test exists so the failure has a name when it does."""
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_every_weight_has_a_signal_and_every_signal_a_weight() -> None:
    produced = {s.name for s in score().signals}
    assert produced == set(WEIGHTS)


# -- normalisation -------------------------------------------------------------------


def test_a_target_date_days_away_is_maximum_urgency() -> None:
    value, why = normalise_target_date(date(2026, 8, 11), today=TODAY)
    assert value == 1.0
    assert "2 day" in why


def test_a_target_date_already_passed_is_still_maximum_urgency() -> None:
    """A deadline that has arrived does not make someone *less* likely to buy, and decaying
    it would quietly demote the most urgent lead on the board."""
    value, why = normalise_target_date(date(2026, 8, 1), today=TODAY)
    assert value == 1.0
    assert "passed" in why


def test_a_distant_target_date_scores_zero_not_negative() -> None:
    value, _ = normalise_target_date(date(2027, 8, 9), today=TODAY)
    assert value == 0.0


def test_an_unstated_target_date_is_low_but_not_zero() -> None:
    """No date is weak evidence of no urgency, not proof of it."""
    value, why = normalise_target_date(None, today=TODAY)
    assert 0.0 < value < 0.5
    assert "no target date" in why


def test_target_date_urgency_decreases_monotonically() -> None:
    values = [
        normalise_target_date(TODAY + timedelta(days=d), today=TODAY)[0] for d in (5, 30, 90, 179)
    ]
    assert values == sorted(values, reverse=True)


def test_a_car_inside_the_budget_fits_perfectly() -> None:
    value, why = normalise_budget_fit(Decimal("30000"), Decimal("24000"))
    assert value == 1.0
    assert "80%" in why


def test_a_car_over_budget_decays_rather_than_falling_off_a_cliff() -> None:
    """A car 10% over what someone said is still a call worth making."""
    slight = normalise_budget_fit(Decimal("30000"), Decimal("33000"))[0]
    heavy = normalise_budget_fit(Decimal("30000"), Decimal("42000"))[0]
    assert 0.0 < heavy < slight < 1.0


def test_a_car_far_over_budget_bottoms_out_at_zero() -> None:
    assert normalise_budget_fit(Decimal("10000"), Decimal("60000"))[0] == 0.0


def test_a_missing_budget_and_a_missing_price_say_which_is_missing() -> None:
    assert "budget" in normalise_budget_fit(None, Decimal("20000"))[1]
    assert "price" in normalise_budget_fit(Decimal("20000"), None)[1]


def test_return_sessions_saturate() -> None:
    assert normalise_return_sessions(1)[0] == 0.0
    assert normalise_return_sessions(2)[0] == 0.5
    assert normalise_return_sessions(3)[0] == 1.0
    assert normalise_return_sessions(50)[0] == 1.0


# -- the score (gate 15.3's shape) ---------------------------------------------------


def test_contributions_sum_to_the_score() -> None:
    result = score(
        events=EVERYTHING,
        target_date=date(2026, 8, 12),
        budget=Decimal("30000"),
        price=Decimal("25000"),
    )
    assert abs(result.score - sum(s.contribution for s in result.signals)) < 1e-9


def test_every_contribution_is_weight_times_value() -> None:
    for signal in score(events=CART_AND_CHECKOUT).signals:
        assert abs(signal.contribution - signal.weight * signal.value) < 1e-9


def test_the_score_never_leaves_zero_to_one() -> None:
    lowest = score(
        events=CART, target_date=date(2030, 1, 1), budget=Decimal("1"), price=Decimal("100000")
    )
    highest = score(
        events=EVERYTHING,
        target_date=TODAY,
        budget=Decimal("100000"),
        price=Decimal("10000"),
        return_sessions=9,
        is_corporate=True,
    )
    assert 0.0 <= lowest.score <= highest.score <= 1.0


def test_every_signal_carries_a_sentence_not_just_a_number() -> None:
    for signal in score().signals:
        assert signal.explanation.strip()


# -- determinism (gate 15.2) ---------------------------------------------------------


def test_the_same_inputs_produce_the_same_score_twice() -> None:
    kwargs = {
        "events": CART_AND_CHECKOUT,
        "target_date": date(2026, 8, 20),
        "today": TODAY,
        "budget": Decimal("28000"),
        "price": Decimal("26500"),
        "return_sessions": 2,
        "is_corporate": True,
    }
    first, second = score_lead(**kwargs), score_lead(**kwargs)  # type: ignore[arg-type]
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_event_order_does_not_change_the_score() -> None:
    """A lead records *which* actions happened. If the order mattered, a buyer who opened
    checkout before the cart-add reached the store would score differently for no reason."""
    forward = score(events=(LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED))
    backward = score(events=(LeadEvent.CHECKOUT_OPENED, LeadEvent.CART_ADD))
    assert forward.score == backward.score
    assert forward.tier is backward.tier


# -- tiers ---------------------------------------------------------------------------


def test_tier_thresholds_are_ordered() -> None:
    assert tier_for(HIGH_THRESHOLD) is IntentTier.HIGH
    assert tier_for(MEDIUM_THRESHOLD) is IntentTier.MEDIUM
    assert tier_for(MEDIUM_THRESHOLD - 0.001) is IntentTier.LOW


def test_a_bare_cart_add_with_no_date_is_low() -> None:
    """PLAN-02 §P15's table: browsing-adjacent behaviour is not a hot lead."""
    assert score(events=CART).tier is IntentTier.LOW


def test_a_cart_add_with_a_date_a_month_out_is_medium() -> None:
    result = score(
        events=CART, target_date=date(2026, 9, 8), budget=Decimal("30000"), price=Decimal("28000")
    )
    assert result.tier is IntentTier.MEDIUM


def test_cart_plus_checkout_days_away_is_high() -> None:
    result = score(
        events=CART_AND_CHECKOUT,
        target_date=date(2026, 8, 14),
        budget=Decimal("30000"),
        price=Decimal("28000"),
    )
    assert result.tier is IntentTier.HIGH


def test_more_engagement_never_lowers_the_score() -> None:
    """Monotonicity is the property that makes the tier explicable: a dealer should never see
    a lead go *down* a tier because the buyer did more."""
    base = score(events=CART).score
    more = score(events=CART_AND_CHECKOUT).score
    most = score(events=EVERYTHING).score
    assert base < more < most


# -- phrasing (gate 15.8's server half) ----------------------------------------------


def test_every_tier_label_is_marked_as_an_estimate() -> None:
    for tier in IntentTier:
        assert "(estimated)" in tier.label


def test_the_explanation_names_the_signals_behind_it() -> None:
    result = score(events=CART_AND_CHECKOUT, target_date=date(2026, 8, 12))
    assert result.explanation.startswith(result.tier.label)
    assert "opened checkout" in result.explanation


# -- income (gate 15.9, D-079) -------------------------------------------------------


def test_the_scorer_takes_no_income_parameter_at_all() -> None:
    """The privacy property is structural, not a rule somebody has to keep following: there
    is no argument to pass income through and no store to reach one through."""
    parameters = set(inspect.signature(score_lead).parameters)
    assert not {p for p in parameters if "income" in p or "band" in p or "salary" in p}


def test_the_module_never_mentions_income() -> None:
    source = inspect.getsource(lead_scoring)
    body = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    # The module docstring explains *why* income is absent, at length -- that is the one
    # place the word is allowed, and it is above the first import.
    code = body.split('"""', 2)[-1]
    for term in ("annual_income", "income_band", "IncomeBand", "salary"):
        assert term not in code, f"{term} reached the scorer's code"


@pytest.mark.parametrize("band", ["under_25k", "25k_50k", "50k_100k", "100k_plus", "undisclosed"])
def test_no_income_band_can_change_a_score(band: str) -> None:
    """There is nowhere to put it. Asserted by construction rather than by comparing two
    scores, because a scorer that accepted the argument and ignored it would pass that test
    and still be one refactor away from using it."""
    with pytest.raises(TypeError):
        score_lead(  # type: ignore[call-arg]
            events=CART,
            target_date=None,
            today=TODAY,
            budget=None,
            price=None,
            income_band=band,
        )
