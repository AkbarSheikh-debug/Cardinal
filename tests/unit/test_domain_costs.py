"""Monthly running-cost formulas (PHASE-5 §4/§5). Every constant is round on purpose so a
result can be checked by inspection, not just re-derived by the same code that produced it.
"""

from __future__ import annotations

from decimal import Decimal

from src.domain.constants import (
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
from src.domain.costs import (
    annual_road_tax,
    monthly_energy,
    monthly_insurance,
    monthly_maintenance,
    monthly_running_cost,
)
from src.domain.enums import EfficiencyUnit, FuelType, PowertrainArchetype, TimingMechanism
from tests.unit.helpers import make_listing


def test_monthly_insurance_is_linear_in_band() -> None:
    band_1 = make_listing(insurance_band=1)
    band_5 = make_listing(insurance_band=5)
    assert monthly_insurance(band_1) == INSURANCE_BASE_MONTHLY + INSURANCE_PER_BAND_MONTHLY
    assert monthly_insurance(band_5) == INSURANCE_BASE_MONTHLY + INSURANCE_PER_BAND_MONTHLY * 5


def test_monthly_energy_petrol_uses_fuel_price_per_litre() -> None:
    listing = make_listing(
        fuel_type=FuelType.PETROL,
        efficiency_value="6",
        efficiency_unit=EfficiencyUnit.L_PER_100KM,
    )
    # 6 L/100km * 1250 km/month / 100 = 75 L; 75 * FUEL_PRICE_PER_LITRE.
    expected = Decimal("75") * FUEL_PRICE_PER_LITRE
    assert monthly_energy(listing, km_per_month=1250) == expected


def test_monthly_energy_electric_uses_electricity_price_per_kwh_not_fuel_price() -> None:
    listing = make_listing(
        fuel_type=FuelType.ELECTRIC,
        efficiency_value="15",
        efficiency_unit=EfficiencyUnit.KWH_PER_100KM,
        timing_mechanism=TimingMechanism.NOT_APPLICABLE,
        service_interval_km=None,
        powertrain_archetype=PowertrainArchetype.BEV_SKATEBOARD,
    )
    expected = Decimal("187.5") * ELECTRICITY_PRICE_PER_KWH
    assert monthly_energy(listing, km_per_month=1250) == expected
    assert monthly_energy(listing, km_per_month=1250) != Decimal("187.5") * FUEL_PRICE_PER_LITRE


def test_monthly_maintenance_belt_surcharge() -> None:
    chain = make_listing(timing_mechanism=TimingMechanism.CHAIN)
    belt = make_listing(timing_mechanism=TimingMechanism.BELT)
    assert monthly_maintenance(belt) - monthly_maintenance(chain) == TIMING_BELT_MONTHLY_SURCHARGE


def test_monthly_maintenance_bev_discount_never_goes_negative() -> None:
    bev = make_listing(
        fuel_type=FuelType.ELECTRIC,
        efficiency_unit=EfficiencyUnit.KWH_PER_100KM,
        timing_mechanism=TimingMechanism.NOT_APPLICABLE,
        service_interval_km=None,
        powertrain_archetype=PowertrainArchetype.BEV_SKATEBOARD,
    )
    combustion = make_listing()
    assert monthly_maintenance(bev) == max(
        Decimal("0"), MAINTENANCE_BASE_MONTHLY - BEV_MAINTENANCE_DISCOUNT_MONTHLY
    )
    assert monthly_maintenance(bev) < monthly_maintenance(combustion)


def test_monthly_running_cost_is_the_sum_of_the_three() -> None:
    listing = make_listing()
    total = monthly_running_cost(listing)
    assert total == (
        monthly_insurance(listing) + monthly_energy(listing) + monthly_maintenance(listing)
    )


def test_annual_road_tax_electric_is_cheaper() -> None:
    petrol = make_listing(fuel_type=FuelType.PETROL)
    electric = make_listing(
        fuel_type=FuelType.ELECTRIC,
        efficiency_unit=EfficiencyUnit.KWH_PER_100KM,
        timing_mechanism=TimingMechanism.NOT_APPLICABLE,
        service_interval_km=None,
        powertrain_archetype=PowertrainArchetype.BEV_SKATEBOARD,
    )
    assert annual_road_tax(petrol) == ROAD_TAX_ANNUAL
    assert annual_road_tax(electric) == ROAD_TAX_ANNUAL_ELECTRIC
    assert annual_road_tax(electric) < annual_road_tax(petrol)
