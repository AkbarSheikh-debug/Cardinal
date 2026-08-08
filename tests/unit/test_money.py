"""`Money` (gate 0.2). Float arithmetic on prices is the bug that shows up in a checkout
screen on demo day, so the type refuses floats rather than rounding them.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.enums import Currency
from src.domain.money import CurrencyMismatchError, Money


def test_rejects_float_construction() -> None:
    with pytest.raises(ValueError, match="must not be constructed from a float"):
        Money(amount=24899.99, currency=Currency.EUR)


def test_accepts_str_int_and_decimal() -> None:
    assert Money.of("24899.99").amount == Decimal("24899.99")
    assert Money.of(24899).amount == Decimal("24899.00")
    assert Money.of(Decimal("0.01")).amount == Decimal("0.01")


def test_arithmetic_preserves_decimal() -> None:
    a, b = Money.of("0.10"), Money.of("0.20")
    total = a + b
    assert isinstance(total.amount, Decimal)
    # The canonical float-error case: 0.1 + 0.2 == 0.30000000000000004.
    assert total.amount == Decimal("0.30")
    assert (a * 3).amount == Decimal("0.30")
    assert (b - a).amount == Decimal("0.10")


def test_refuses_to_scale_by_a_float() -> None:
    with pytest.raises(TypeError):
        Money.of("100") * 1.5  # type: ignore[operator]


def test_currency_mismatch_raises_rather_than_guessing() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money.of("10", Currency.EUR) + Money.of("10", Currency.USD)


def test_comparisons() -> None:
    assert Money.of("10") < Money.of("20")
    assert Money.of("20") >= Money.of("20")


def test_json_round_trip_keeps_it_out_of_float_territory() -> None:
    original = Money.of("24899.99")
    dumped = original.model_dump_json()
    assert '"24899.99"' in dumped, "amount must serialise as a string, not a JSON number"
    assert Money.model_validate_json(dumped) == original


def test_is_frozen() -> None:
    with pytest.raises(ValueError):
        Money.of("1").amount = Decimal("2")  # type: ignore[misc]
