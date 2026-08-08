"""The financing calculator (PHASE-8 §7): pure `Decimal` amortisation, hand-verified against
the standard formula the same way gate 5.6 hand-verified TCO's break-even solver.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.financing import (
    MAX_DOWN_PAYMENT_PCT,
    MAX_TERM_MONTHS,
    MIN_TERM_MONTHS,
    FinancingTerms,
    compute_monthly_payment,
)
from src.domain.money import Money


def test_matches_a_hand_computed_value() -> None:
    # principal = 20000 * 0.90 = 18000; r = 0.069/12; monthly = 18000r / (1 - (1+r)^-60)
    # Hand/independently verified (Decimal and plain float agree to the cent): EUR 355.57.
    terms = FinancingTerms(term_months=60, down_payment_pct=Decimal(10), apr_pct=Decimal("6.9"))
    monthly = compute_monthly_payment(Money.of("20000"), terms)
    assert monthly == Money.of("355.57")


def test_zero_down_payment_uses_the_full_price_as_principal() -> None:
    terms = FinancingTerms(term_months=60, down_payment_pct=Decimal(0), apr_pct=Decimal("6.9"))
    financed = compute_monthly_payment(Money.of("20000"), terms)
    down = FinancingTerms(term_months=60, down_payment_pct=Decimal(10), apr_pct=Decimal("6.9"))
    with_down_payment = compute_monthly_payment(Money.of("20000"), down)
    assert financed > with_down_payment


def test_zero_apr_spreads_the_principal_evenly_across_the_term() -> None:
    terms = FinancingTerms(term_months=50, down_payment_pct=Decimal(0), apr_pct=Decimal(0))
    monthly = compute_monthly_payment(Money.of("10000"), terms)
    assert monthly == Money.of("200.00")


def test_a_higher_apr_never_lowers_the_monthly_payment() -> None:
    low = FinancingTerms(term_months=48, down_payment_pct=Decimal(10), apr_pct=Decimal("2"))
    high = FinancingTerms(term_months=48, down_payment_pct=Decimal(10), apr_pct=Decimal("12"))
    assert compute_monthly_payment(Money.of("15000"), high) > compute_monthly_payment(
        Money.of("15000"), low
    )


def test_a_longer_term_never_raises_the_monthly_payment() -> None:
    short = FinancingTerms(term_months=24, down_payment_pct=Decimal(10), apr_pct=Decimal("6.9"))
    long_ = FinancingTerms(term_months=72, down_payment_pct=Decimal(10), apr_pct=Decimal("6.9"))
    assert compute_monthly_payment(Money.of("15000"), long_) < compute_monthly_payment(
        Money.of("15000"), short
    )


def test_term_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError):
        FinancingTerms(
            term_months=MIN_TERM_MONTHS - 1, down_payment_pct=Decimal(0), apr_pct=Decimal(0)
        )
    with pytest.raises(ValidationError):
        FinancingTerms(
            term_months=MAX_TERM_MONTHS + 1, down_payment_pct=Decimal(0), apr_pct=Decimal(0)
        )


def test_down_payment_bound_is_enforced() -> None:
    with pytest.raises(ValidationError):
        FinancingTerms(
            term_months=60, down_payment_pct=MAX_DOWN_PAYMENT_PCT + 1, apr_pct=Decimal(0)
        )
