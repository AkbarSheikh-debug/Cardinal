"""Total cost of ownership contracts.

PHASE-5 §5 owns the arithmetic. P0 fixes the shape, and the shape carries one opinion: the
output is *itemised*. A single number is unpersuasive; a breakdown is an argument, and it
lets the UI show where the money goes.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from itertools import pairwise
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.constants import AVG_KM_PER_MONTH, REGISTRATION_FEE, TRANSFER_FEE
from src.domain.costs import (
    annual_road_tax,
    monthly_energy,
    monthly_insurance,
    monthly_maintenance,
)
from src.domain.listing import Listing
from src.domain.money import Money


class TcoPath(StrEnum):
    BUY = "buy"
    RENT = "rent"


class TcoLineKind(StrEnum):
    PURCHASE = "purchase"
    RENTAL = "rental"
    REGISTRATION = "registration"
    DEPRECIATION = "depreciation"
    INSURANCE = "insurance"
    ENERGY = "energy"
    MAINTENANCE = "maintenance"
    TAX = "tax"
    EXCESS_MILEAGE = "excess_mileage"
    RESALE = "resale"


class TcoLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: TcoLineKind
    amount: Money = Field(description="Negative for money coming back, e.g. resale.")
    note: str = ""


class TcoEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: TcoPath
    horizon_months: int = Field(gt=0)
    lines: tuple[TcoLine, ...]
    total: Money

    @model_validator(mode="after")
    def _total_is_the_sum(self) -> Self:
        if not self.lines:
            raise ValueError("a TCO estimate with no line items explains nothing")
        running = self.lines[0].amount
        for line in self.lines[1:]:
            running = running + line.amount
        if running != self.total:
            raise ValueError(f"total {self.total} does not equal the sum of lines {running}")
        return self


class TcoComparison(BaseModel):
    """The rent-vs-buy answer."""

    model_config = ConfigDict(frozen=True)

    buy: TcoEstimate
    rent: TcoEstimate
    break_even_month: int | None = Field(
        default=None,
        description="First month where cumulative buy < cumulative rent. None if it never crosses "
        "inside the horizon -- which is a real answer, not a missing one.",
    )


# ==============================================================================================
# The TCO engine (PHASE-5 SS5). Every recurring line is itemised rather than folded into one
# figure -- a single number is unpersuasive, a breakdown is an argument -- and every constant
# it depends on lives in `src/domain/constants.py` with a source comment (PHASE-5 SS10's own
# risk mitigation for "TCO looks authoritative but rests on invented constants").
# ==============================================================================================


def residual_fraction_at_month(
    curve: tuple[float, float, float, float, float], months: int
) -> float:
    """`depreciation_curve` only carries annual points (years 1..5); the break-even solver
    needs a value at every month. Linear interpolation between (0, 1.0) and each year's point
    is a curve, not a flat rate, so the six-month region -- exactly where rent-vs-buy is
    decided (PHASE-5 SS5) -- doesn't collapse to a straight line between two annual anchors
    far apart. Past year 5 the last known fraction holds rather than extrapolating below it.
    """
    if months <= 0:
        return 1.0
    points: list[tuple[int, float]] = [(0, 1.0)] + [((i + 1) * 12, curve[i]) for i in range(5)]
    if months >= points[-1][0]:
        return points[-1][1]
    for (m0, f0), (m1, f1) in pairwise(points):
        if m0 <= months <= m1:
            t = (months - m0) / (m1 - m0)
            return f0 + t * (f1 - f0)
    raise AssertionError("unreachable: months bounded above by the last curve point")


def compute_buy_tco(listing: Listing, horizon_months: int) -> TcoEstimate:
    """Purchase + registration + insurance + energy + maintenance + tax - resale, itemised
    (PHASE-5 SS5's buy path). Resale is a curve-derived value net of the transfer-fee
    friction on the way out, not the sticker price times a flat annual rate.
    """
    if listing.price_buy is None:
        raise ValueError(f"{listing.source}:{listing.source_id} has no purchase price to TCO")

    lines = [
        TcoLine(kind=TcoLineKind.PURCHASE, amount=listing.price_buy),
        TcoLine(kind=TcoLineKind.REGISTRATION, amount=Money.of(REGISTRATION_FEE)),
        TcoLine(
            kind=TcoLineKind.INSURANCE,
            amount=Money.of(monthly_insurance(listing) * horizon_months),
            note=f"EUR {monthly_insurance(listing)}/month x {horizon_months}",
        ),
        TcoLine(
            kind=TcoLineKind.ENERGY,
            amount=Money.of(monthly_energy(listing) * horizon_months),
            note=f"EUR {monthly_energy(listing)}/month x {horizon_months}",
        ),
        TcoLine(
            kind=TcoLineKind.MAINTENANCE,
            amount=Money.of(monthly_maintenance(listing) * horizon_months),
        ),
        TcoLine(
            kind=TcoLineKind.TAX,
            amount=Money.of(annual_road_tax(listing) / Decimal(12) * horizon_months),
        ),
    ]
    fraction = residual_fraction_at_month(listing.depreciation_curve, horizon_months)
    resale_gross = listing.market_value.amount * Decimal(str(fraction))
    resale_net = max(Decimal("0"), resale_gross - TRANSFER_FEE)
    lines.append(
        TcoLine(
            kind=TcoLineKind.RESALE,
            amount=Money.of(-resale_net),
            note=f"{round(fraction * 100)}% of market value, less EUR {TRANSFER_FEE} transfer fee",
        )
    )

    total = lines[0].amount
    for line in lines[1:]:
        total = total + line.amount
    return TcoEstimate(
        path=TcoPath.BUY, horizon_months=horizon_months, lines=tuple(lines), total=total
    )


def compute_rent_tco(
    listing: Listing, horizon_months: int, *, km_per_month: int = AVG_KM_PER_MONTH
) -> TcoEstimate:
    """Monthly-tier rental price + energy + excess mileage, itemised (PHASE-5 SS5's rent
    path). The rental line is always `rental_rates.monthly x horizon_months` -- never
    `daily x 30` -- which is what makes the tiers' nonlinearity show up in the output rather
    than inflating the rent path so buying always "wins" (gate 5.7).
    """
    if listing.rental_rates is None:
        raise ValueError(f"{listing.source}:{listing.source_id} has no rental rates to TCO")
    rates = listing.rental_rates

    lines = [
        TcoLine(
            kind=TcoLineKind.RENTAL,
            amount=rates.monthly * horizon_months,
            note=f"EUR {rates.monthly.amount}/month tier x {horizon_months} (not daily x 30)",
        )
    ]
    if not rates.insurance_included:
        lines.append(
            TcoLine(
                kind=TcoLineKind.INSURANCE,
                amount=Money.of(monthly_insurance(listing) * horizon_months),
            )
        )
    lines.append(
        TcoLine(
            kind=TcoLineKind.ENERGY,
            amount=Money.of(monthly_energy(listing, km_per_month=km_per_month) * horizon_months),
        )
    )
    included_km_per_month = rates.included_km_per_day * 30
    if km_per_month > included_km_per_month:
        excess_km = (km_per_month - included_km_per_month) * horizon_months
        lines.append(
            TcoLine(
                kind=TcoLineKind.EXCESS_MILEAGE,
                amount=rates.excess_km_rate * excess_km,
                note=f"{excess_km} km over the included allowance at "
                f"EUR {rates.excess_km_rate.amount}/km",
            )
        )

    total = lines[0].amount
    for line in lines[1:]:
        total = total + line.amount
    return TcoEstimate(
        path=TcoPath.RENT, horizon_months=horizon_months, lines=tuple(lines), total=total
    )


def _break_even_month(
    listing: Listing, max_months: int, *, km_per_month: int = AVG_KM_PER_MONTH
) -> int | None:
    for month in range(1, max(max_months, 1) + 1):
        buy_total = compute_buy_tco(listing, month).total
        rent_total = compute_rent_tco(listing, month, km_per_month=km_per_month).total
        if buy_total < rent_total:
            return month
    return None


def compute_comparison(
    listing: Listing, horizon_months: int, *, km_per_month: int = AVG_KM_PER_MONTH
) -> TcoComparison:
    """The rent-vs-buy answer (PHASE-5 SS5): both paths at the stated horizon, plus the first
    month the buy path's cumulative cost undercuts the rent path's -- solved by walking the
    same two functions month by month rather than a closed form, since resale is a curve, not
    a rate.
    """
    buy = compute_buy_tco(listing, horizon_months)
    rent = compute_rent_tco(listing, horizon_months, km_per_month=km_per_month)
    break_even = _break_even_month(listing, horizon_months, km_per_month=km_per_month)
    return TcoComparison(buy=buy, rent=rent, break_even_month=break_even)
