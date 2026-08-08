"""Money — `Decimal` inside, never a float.

CONSTITUTION / PHASE-0 §4: float arithmetic on prices produces `EUR 24,899.999999` in a
checkout screen, and it will happen on demo day. So `Money` refuses to be built from a
float at all rather than rounding one quietly, and every operator returns `Money`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from src.domain.enums import Currency

CENTS = Decimal("0.01")


class CurrencyMismatchError(ValueError):
    """Raised when two `Money` values in different currencies are combined.

    There is no ambient exchange rate in the domain layer -- fetching one would be I/O,
    which `src/domain` is not allowed to do. Conversion belongs to a caller that has a rate.
    """

    def __init__(self, left: Currency, right: Currency) -> None:
        super().__init__(f"cannot combine {left} with {right} without an explicit rate")


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Decimal
    currency: Currency

    @field_validator("amount", mode="before")
    @classmethod
    def _reject_float(cls, value: Any) -> Any:
        # Pydantic would happily coerce 24899.999999999996 into a Decimal carrying every
        # bit of that binary error. Refuse at the door; callers pass str/int/Decimal.
        if isinstance(value, float):
            raise ValueError(
                "Money.amount must not be constructed from a float; "
                "pass a str, int or Decimal (e.g. Money(amount='24899.99', currency='EUR'))"
            )
        return value

    @field_validator("amount")
    @classmethod
    def _quantise(cls, value: Decimal) -> Decimal:
        return value.quantize(CENTS, rounding=ROUND_HALF_UP)

    @field_serializer("amount")
    def _serialise_amount(self, value: Decimal) -> str:
        # A JSON number would put this straight back into float territory on the way out.
        return str(value)

    # -- constructors -------------------------------------------------------------

    @classmethod
    def of(cls, amount: str | int | Decimal, currency: Currency = Currency.EUR) -> Self:
        return cls(amount=Decimal(amount), currency=currency)

    @classmethod
    def zero(cls, currency: Currency = Currency.EUR) -> Self:
        return cls(amount=Decimal(0), currency=currency)

    # -- arithmetic ---------------------------------------------------------------

    def _check(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: int | Decimal) -> Money:
        if isinstance(factor, float):
            raise TypeError("refusing to scale Money by a float; use Decimal(str(x))")
        return Money(amount=self.amount * Decimal(factor), currency=self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        return Money(amount=-self.amount, currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.amount >= other.amount

    def __str__(self) -> str:
        return f"{self.currency} {self.amount:,.2f}"
