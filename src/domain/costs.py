"""Shared monthly running-cost formulas.

One place so P5's `running_cost` scoring criterion (`src/domain/ranking.py`) and the TCO
engine's insurance/energy/maintenance line items (`src/domain/tco.py`) can never silently
diverge on what a listing actually costs to run per month -- both call through here rather
than each carrying its own copy of the arithmetic.
"""

from __future__ import annotations

from decimal import Decimal

from src.domain.constants import (
    AVG_KM_PER_MONTH,
    BEV_MAINTENANCE_DISCOUNT_MONTHLY,
    ELECTRICITY_PRICE_PER_KWH,
    FUEL_PRICE_PER_LITRE,
    INSURANCE_BASE_MONTHLY,
    INSURANCE_PER_BAND_MONTHLY,
    MAINTENANCE_BASE_MONTHLY,
    ROAD_TAX_ANNUAL,
    ROAD_TAX_ANNUAL_ELECTRIC,
    TIMING_BELT_MONTHLY_SURCHARGE,
)
from src.domain.enums import EfficiencyUnit, TimingMechanism
from src.domain.listing import Listing


def monthly_insurance(listing: Listing) -> Decimal:
    return INSURANCE_BASE_MONTHLY + INSURANCE_PER_BAND_MONTHLY * listing.insurance_band


def monthly_energy(listing: Listing, *, km_per_month: int = AVG_KM_PER_MONTH) -> Decimal:
    """EV per-kWh vs petrol/diesel per-litre, from the listing's own `efficiency` field
    (PHASE-5 SS5) -- never one flat per-km figure for every powertrain.
    """
    consumption_per_km = listing.efficiency.value / Decimal(100)
    price = (
        ELECTRICITY_PRICE_PER_KWH
        if listing.efficiency.unit is EfficiencyUnit.KWH_PER_100KM
        else FUEL_PRICE_PER_LITRE
    )
    return consumption_per_km * km_per_month * price


def monthly_maintenance(listing: Listing) -> Decimal:
    amount = MAINTENANCE_BASE_MONTHLY
    if listing.timing_mechanism is TimingMechanism.BELT:
        amount += TIMING_BELT_MONTHLY_SURCHARGE
    if listing.service_interval_km is None:  # BEV: no oil service to schedule at all
        amount -= BEV_MAINTENANCE_DISCOUNT_MONTHLY
    return max(Decimal("0"), amount)


def monthly_running_cost(listing: Listing) -> Decimal:
    """Insurance + energy + maintenance -- the population `running_cost` z-scores against
    (PHASE-5 SS4) and the three recurring TCO lines that aren't rent/purchase/tax/resale.
    """
    return monthly_insurance(listing) + monthly_energy(listing) + monthly_maintenance(listing)


def annual_road_tax(listing: Listing) -> Decimal:
    return ROAD_TAX_ANNUAL_ELECTRIC if listing.fuel_type.is_electric_only else ROAD_TAX_ANNUAL
