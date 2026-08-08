"""Hand-built `Listing` fixtures for P5 tests that need exact, hand-verifiable numbers --
the seeded catalogue (`tests/conftest.py`'s `catalogue` fixture) is real but its prices and
curves aren't round enough to hand-check a TCO or scoring result against.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from src.domain.enums import (
    EfficiencyUnit,
    FuelType,
    OfferType,
    PowertrainArchetype,
    TimingMechanism,
    Transmission,
    VehicleCategory,
)
from src.domain.listing import Efficiency, Listing, Location, RentalRates, listing_uuid
from src.domain.money import Money

_LOCATION = Location(city="Berlin", country="DE", latitude=52.5, longitude=13.4)


def make_listing(
    *,
    source: str = "fixture",
    source_id: str = "FIX-1",
    category: VehicleCategory = VehicleCategory.SEDAN,
    offer_type: OfferType = OfferType.BOTH,
    market_value: str = "20000",
    price_buy: str | None = "20000",
    rental_daily: str | None = "25",
    rental_weekly: str | None = "140",
    rental_monthly: str | None = "500",
    included_km_per_day: int = 60,
    excess_km_rate: str = "0.30",
    insurance_included: bool = True,
    mileage_km: int = 10000,
    fuel_type: FuelType = FuelType.PETROL,
    efficiency_value: str = "6",
    efficiency_unit: EfficiencyUnit = EfficiencyUnit.L_PER_100KM,
    depreciation_curve: tuple[float, float, float, float, float] = (0.80, 0.65, 0.55, 0.48, 0.42),
    insurance_band: int = 1,
    service_interval_km: int | None = 15000,
    timing_mechanism: TimingMechanism = TimingMechanism.CHAIN,
    powertrain_archetype: PowertrainArchetype = PowertrainArchetype.I4_NA,
    available_from: date = date(2026, 1, 1),
    year: int = 2024,
) -> Listing:
    rental_rates = None
    if offer_type.is_rentable:
        assert rental_daily and rental_weekly and rental_monthly
        rental_rates = RentalRates(
            daily=Money.of(rental_daily),
            weekly=Money.of(rental_weekly),
            monthly=Money.of(rental_monthly),
            included_km_per_day=included_km_per_day,
            excess_km_rate=Money.of(excess_km_rate),
            insurance_included=insurance_included,
        )
    return Listing(
        id=listing_uuid(source, source_id),
        source=source,
        source_id=source_id,
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        raw={"fixture": True},
        brand="Test",
        model="Model",
        variant="Base",
        year=year,
        category=category,
        offer_type=offer_type,
        market_value=Money.of(market_value),
        price_buy=Money.of(price_buy) if offer_type.is_buyable and price_buy else None,
        rental_rates=rental_rates,
        mileage_km=mileage_km,
        fuel_type=fuel_type,
        transmission=Transmission.MANUAL,
        seats=5,
        doors=4,
        efficiency=Efficiency(value=Decimal(efficiency_value), unit=efficiency_unit),
        depreciation_curve=depreciation_curve,
        insurance_band=insurance_band,
        service_interval_km=service_interval_km,
        timing_mechanism=timing_mechanism,
        powertrain_archetype=powertrain_archetype,
        location=_LOCATION,
        available_from=available_from,
        description="a fixture listing",
    )
