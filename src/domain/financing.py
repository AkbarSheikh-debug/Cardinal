"""The financing calculator (PHASE-8 §7): term / APR / down payment -> monthly payment.

Pure `Decimal` arithmetic over primitives, the same discipline D-020 established for
`domain/scoring.py` -- a function of numbers, not of a `Booking` or a `Listing`, so it is
property-testable with no fixture and safely callable from both the checkout App's own
client-side estimate and this module's server-side recomputation on submit (PHASE-8 §7:
"the displayed figure is never trusted"). The two call sites necessarily run in two different
languages (browser JS, backend Python); `tests/unit/test_domain_financing.py` pins the exact
values `web/src/mcp-host` (or, here, the checkout App's own inline script) has to reproduce
bit-for-bit, the same cross-language-parity discipline D-034 used for CSP.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.money import Money

MIN_TERM_MONTHS = 12
MAX_TERM_MONTHS = 72
MAX_DOWN_PAYMENT_PCT = Decimal("40")

_CENTS = Decimal("0.01")


class FinancingTerms(BaseModel):
    """What the App exposes: term, down payment percentage, and an APR (PHASE-8 §7)."""

    model_config = ConfigDict(frozen=True)

    term_months: int = Field(ge=MIN_TERM_MONTHS, le=MAX_TERM_MONTHS)
    down_payment_pct: Decimal = Field(ge=Decimal("0"), le=MAX_DOWN_PAYMENT_PCT)
    apr_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))


def compute_monthly_payment(price: Money, terms: FinancingTerms) -> Money:
    """Standard amortisation:

        principal = price * (1 - down%)
        r = apr / 12
        monthly = principal * r / (1 - (1 + r)^-term)

    `r == 0` (a 0% APR promotion, or an APR left at zero in a quick estimate) is not a
    special case in the real world but *is* one in this formula -- the closed form divides
    by `1 - 1 = 0` -- so it falls back to the terms every reader already knows: principal
    spread evenly across the term.
    """
    down_fraction = terms.down_payment_pct / Decimal(100)
    principal = price.amount * (Decimal(1) - down_fraction)
    monthly_rate = (terms.apr_pct / Decimal(100)) / Decimal(12)

    if monthly_rate == 0:
        monthly = principal / Decimal(terms.term_months)
    else:
        denominator = Decimal(1) - (Decimal(1) + monthly_rate) ** (-terms.term_months)
        monthly = principal * monthly_rate / denominator

    quantised = monthly.quantize(_CENTS, rounding=ROUND_HALF_UP)
    return Money(amount=quantised, currency=price.currency)
