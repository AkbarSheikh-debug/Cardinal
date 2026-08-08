"""The TCO engine (PHASE-5 §5, §9). `test_break_even_matches_hand_computation` pins the
exact fixture and arithmetic gate 5.6 asserts -- see DECISIONS.md for the worked derivation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.enums import OfferType
from src.domain.listing import Listing
from src.domain.money import Money
from src.domain.tco import (
    compute_buy_tco,
    compute_comparison,
    compute_rent_tco,
    residual_fraction_at_month,
)
from tests.unit.helpers import make_listing


def test_residual_fraction_at_month_zero_is_full_value() -> None:
    assert residual_fraction_at_month((0.8, 0.65, 0.55, 0.48, 0.42), 0) == 1.0


def test_residual_fraction_interpolates_linearly_within_year_one() -> None:
    curve = (0.8, 0.65, 0.55, 0.48, 0.42)
    assert residual_fraction_at_month(curve, 12) == pytest.approx(0.8)
    assert residual_fraction_at_month(curve, 6) == pytest.approx(0.9)  # halfway to 0.8


def test_residual_fraction_holds_the_last_point_beyond_year_five() -> None:
    curve = (0.8, 0.65, 0.55, 0.48, 0.42)
    assert residual_fraction_at_month(curve, 61) == curve[-1]
    assert residual_fraction_at_month(curve, 600) == curve[-1]


def test_compute_buy_tco_requires_a_purchase_price() -> None:
    rent_only = make_listing(offer_type=OfferType.RENT)
    with pytest.raises(ValueError, match="no purchase price"):
        compute_buy_tco(rent_only, 12)


def test_compute_rent_tco_requires_rental_rates() -> None:
    buy_only = make_listing(offer_type=OfferType.BUY)
    with pytest.raises(ValueError, match="no rental rates"):
        compute_rent_tco(buy_only, 12)


def test_rental_line_uses_the_monthly_tier_not_daily_times_thirty() -> None:
    """Gate 5.7: rental pricing tiers applied -- weekly/monthly rate != daily x 7/30."""
    listing = make_listing(rental_daily="25", rental_weekly="140", rental_monthly="500")
    assert listing.rental_rates is not None
    naive_daily_times_30 = listing.rental_rates.daily.amount * 30
    assert listing.rental_rates.monthly.amount != naive_daily_times_30

    estimate = compute_rent_tco(listing, 1)
    rental_line = next(line for line in estimate.lines if line.kind.value == "rental")
    assert rental_line.amount == listing.rental_rates.monthly
    assert rental_line.amount.amount != naive_daily_times_30


def test_rent_tco_adds_excess_mileage_when_allowance_is_exceeded() -> None:
    listing = make_listing(included_km_per_day=10)  # 300 km/month included, well under 1250
    estimate = compute_rent_tco(listing, 1, km_per_month=1250)
    kinds = {line.kind.value for line in estimate.lines}
    assert "excess_mileage" in kinds


def test_rent_tco_skips_excess_mileage_when_allowance_covers_it() -> None:
    listing = make_listing(included_km_per_day=60)  # 1800 km/month, covers 1250
    estimate = compute_rent_tco(listing, 1, km_per_month=1250)
    kinds = {line.kind.value for line in estimate.lines}
    assert "excess_mileage" not in kinds


def test_tco_estimate_lines_sum_to_total() -> None:
    listing = make_listing()
    buy = compute_buy_tco(listing, 12)
    running = buy.lines[0].amount
    for line in buy.lines[1:]:
        running = running + line.amount
    assert running == buy.total


# -- gate 5.6's fixture: hand-computed break-even --------------------------------------------
#
# price_buy = market_value = EUR 20,000; depreciation year 1 = 0.80; rental monthly = EUR 500;
# insurance band 1 (EUR 42/month); petrol 6 L/100km (EUR 131.25/month energy); chain timing +
# a service interval (EUR 25/month maintenance, no belt surcharge, no BEV discount); flat
# combustion road tax (EUR 140/year = EUR 11.6667/month); registration EUR 250; transfer fee
# EUR 120; rental insurance included, 60 km/day allowance (no excess mileage at 1250 km/month).
#
# Buy(h)  = 20000 + 250 + (42 + 131.25 + 25 + 11.6667)h - (20000*(1 - 0.2h/12) - 120)
#         = 370 + 543.25h   (h <= 12)
# Rent(h) = 500h + 131.25h = 631.25h
# Buy(h) < Rent(h)  <=>  h > 370/88 = 4.204...  ->  first integer month = 5
#   Buy(5)  = 370 + 543.25*5  = 3086.25
#   Rent(5) = 631.25*5        = 3156.25


def _gate_5_6_fixture() -> Listing:
    return make_listing(
        market_value="20000",
        price_buy="20000",
        rental_daily="25",
        rental_weekly="140",
        rental_monthly="500",
        included_km_per_day=60,
        insurance_included=True,
        insurance_band=1,
        efficiency_value="6",
        depreciation_curve=(0.80, 0.65, 0.55, 0.48, 0.42),
    )


def test_break_even_matches_hand_computation() -> None:
    listing = _gate_5_6_fixture()
    comparison = compute_comparison(listing, 12)
    assert comparison.break_even_month == 5

    buy_5 = compute_buy_tco(listing, 5).total
    rent_5 = compute_rent_tco(listing, 5).total
    assert abs(buy_5.amount - Decimal("3086.25")) <= Decimal("50")
    assert abs(rent_5.amount - Decimal("3156.25")) <= Decimal("50")
    assert buy_5 < rent_5


def test_break_even_is_none_when_it_never_crosses_inside_the_horizon() -> None:
    listing = _gate_5_6_fixture()
    # The crossover is month 5; a 3-month horizon never reaches it.
    comparison = compute_comparison(listing, 3)
    assert comparison.break_even_month is None


def test_tco_illustrative_constants_are_centralised() -> None:
    """PHASE-5 §10's own risk mitigation: every constant lives in one file. This just pins
    that `Money.of` accepts them directly, so a constants.py refactor that breaks the type
    contract fails here instead of silently producing a wrong total.
    """
    from src.domain.constants import REGISTRATION_FEE

    assert Money.of(REGISTRATION_FEE).amount == REGISTRATION_FEE
