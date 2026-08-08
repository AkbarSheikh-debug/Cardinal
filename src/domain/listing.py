"""The canonical vehicle record. Every adapter normalises to this (CONSTITUTION II.6).

Two fields carry more weight than they look like they should:

- `raw` is the untouched upstream payload, and it is required to be non-empty. When a real
  adapter lands and a field turns out to be mapped wrong, historical rows can be
  re-normalised instead of re-fetched.
- `description` is untrusted third-party prose (CONSTITUTION I.4). It is *not* an input to
  ranking -- P5's scorer reads structured fields only -- which is what makes prompt
  injection through listing text economically pointless rather than merely filtered.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.enums import (
    EfficiencyUnit,
    FuelType,
    OfferType,
    PowertrainArchetype,
    TimingMechanism,
    Transmission,
    VehicleCategory,
)
from src.domain.money import Money

SCHEMA_VERSION = "1.0"

#: Stable namespace so `listing_uuid(source, source_id)` is reproducible across processes
#: and across seed runs -- gate 1.6 compares two seed runs byte for byte.
LISTING_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def listing_uuid(source: str, source_id: str) -> uuid.UUID:
    """Derive a listing's primary key from its natural key.

    `UNIQUE (source, source_id)` is the deduplication primitive (PHASE-1 §6); deriving the
    UUID from it means re-seeding is idempotent without a lookup.
    """
    return uuid.uuid5(LISTING_NAMESPACE, f"{source}:{source_id}")


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)

    city: str
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class RentalRates(BaseModel):
    """Rental pricing is nonlinear -- weekly is not daily x 7 (PHASE-5 §5).

    Modelling the tiers explicitly is what stops the rent path being inflated so that
    buying always "wins" the break-even comparison.
    """

    model_config = ConfigDict(frozen=True)

    daily: Money
    weekly: Money
    monthly: Money
    included_km_per_day: int = Field(gt=0)
    excess_km_rate: Money
    insurance_included: bool

    @model_validator(mode="after")
    def _tiers_must_taper(self) -> Self:
        # A weekly rate at or above 7x daily is a data bug, not a pricing strategy.
        if self.weekly >= self.daily * 7:
            raise ValueError("weekly rate must be cheaper than 7x the daily rate")
        if self.monthly >= self.weekly * 4:
            raise ValueError("monthly rate must be cheaper than 4x the weekly rate")
        return self


class Efficiency(BaseModel):
    """Consumption plus the unit it is measured in. See `EfficiencyUnit`."""

    model_config = ConfigDict(frozen=True)

    value: Decimal = Field(gt=0)
    unit: EfficiencyUnit


class Listing(BaseModel):
    """A vehicle as offered by one marketplace.

    Not frozen: `withdrawn_at` is genuinely mutable state (PHASE-1 §6 uses a soft delete so
    a booking referencing a pulled listing still resolves). Everything else is written once
    at normalisation time.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: uuid.UUID
    schema_version: str = SCHEMA_VERSION

    # -- provenance ---------------------------------------------------------------
    source: str = Field(min_length=1, description="Adapter name, e.g. 'mock_autobazaar'")
    source_id: str = Field(min_length=1, description="The marketplace's own id, e.g. 'AB-4471'")
    fetched_at: datetime
    withdrawn_at: datetime | None = None
    raw: dict[str, Any] = Field(min_length=1, description="Untouched upstream payload")

    # -- identity -----------------------------------------------------------------
    brand: str = Field(min_length=1)
    model: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    year: int = Field(ge=1990, le=2100)
    category: VehicleCategory

    # -- commercial ---------------------------------------------------------------
    offer_type: OfferType
    market_value: Money = Field(
        description=(
            "What the vehicle is worth. Present on every listing, including rent-only ones, "
            "because depreciation and resale are what make rent-vs-buy computable at all."
        )
    )
    price_buy: Money | None = Field(
        default=None, description="Asking price. Present iff the listing is buyable."
    )
    rental_rates: RentalRates | None = Field(
        default=None, description="Present iff the listing is rentable."
    )

    # -- physical -----------------------------------------------------------------
    mileage_km: int = Field(ge=0)
    fuel_type: FuelType
    transmission: Transmission
    seats: int = Field(ge=2, le=9)
    doors: int = Field(ge=2, le=5)
    efficiency: Efficiency

    # -- reasoning-layer fields (PHASE-1 §4) ---------------------------------------
    # These exist now because P5's TCO engine and P6's PowertrainExplainer need them.
    # Generating them at seed time costs nothing; retrofitting 240 rows costs an afternoon.
    depreciation_curve: tuple[float, float, float, float, float] = Field(
        description="Fraction of market_value retained at end of years 1..5. Monotonic decreasing."
    )
    insurance_band: int = Field(ge=1, le=20)
    service_interval_km: int | None = Field(
        default=None, ge=1, description="None for BEVs -- there is no oil service to schedule."
    )
    timing_mechanism: TimingMechanism
    powertrain_archetype: PowertrainArchetype

    # -- availability & presentation ------------------------------------------------
    location: Location
    available_from: date
    description: str = Field(
        description="UNTRUSTED third-party prose. Never an input to ranking (CONSTITUTION I.4)."
    )

    # -- invariants -----------------------------------------------------------------

    @model_validator(mode="after")
    def _offer_type_matches_pricing(self) -> Self:
        if self.offer_type.is_buyable and self.price_buy is None:
            raise ValueError(f"offer_type={self.offer_type} requires price_buy")
        if not self.offer_type.is_buyable and self.price_buy is not None:
            raise ValueError(f"offer_type={self.offer_type} must not carry price_buy")
        if self.offer_type.is_rentable and self.rental_rates is None:
            raise ValueError(f"offer_type={self.offer_type} requires rental_rates")
        if not self.offer_type.is_rentable and self.rental_rates is not None:
            raise ValueError(f"offer_type={self.offer_type} must not carry rental_rates")
        return self

    @model_validator(mode="after")
    def _depreciation_curve_is_monotonic(self) -> Self:
        curve = self.depreciation_curve
        if not all(0.0 < point <= 1.0 for point in curve):
            raise ValueError("every depreciation_curve point must be in (0, 1]")
        if any(later > earlier for earlier, later in pairwise(curve)):
            raise ValueError("depreciation_curve must be non-increasing")
        return self

    @model_validator(mode="after")
    def _electric_drivetrain_is_coherent(self) -> Self:
        # PHASE-1 §4.1: EVs get timing_mechanism n-a and no service interval. A BEV with a
        # timing belt is the single most obvious tell that a catalogue is randomly generated.
        if self.fuel_type.is_electric_only:
            if self.timing_mechanism is not TimingMechanism.NOT_APPLICABLE:
                raise ValueError("an electric vehicle has no timing belt or chain")
            if self.service_interval_km is not None:
                raise ValueError("an electric vehicle has no oil service interval")
            if self.efficiency.unit is not EfficiencyUnit.KWH_PER_100KM:
                raise ValueError("an electric vehicle's efficiency must be kWh/100km")
            if self.powertrain_archetype is not PowertrainArchetype.BEV_SKATEBOARD:
                raise ValueError("an electric vehicle must use the BEV skateboard archetype")
        elif self.timing_mechanism is TimingMechanism.NOT_APPLICABLE:
            raise ValueError("a combustion vehicle must declare belt or chain")
        return self

    @property
    def is_available(self) -> bool:
        return self.withdrawn_at is None

    @property
    def natural_key(self) -> tuple[str, str]:
        return (self.source, self.source_id)

    def residual_value(self, years: int) -> Money:
        """Value retained after `years`, from the curve rather than a flat rate.

        Loss is front-loaded, and the six-month region is exactly where rent-vs-buy is
        decided -- a flat 15%/yr gets that answer badly wrong (PHASE-5 §5).
        """
        if not 1 <= years <= 5:
            raise ValueError("depreciation_curve covers years 1..5")
        fraction = Decimal(str(self.depreciation_curve[years - 1]))
        return self.market_value * fraction


class ListingSummary(BaseModel):
    """What `search` returns. Never a full `Listing`.

    Result-size discipline starts in P1, not P2 (PHASE-1 §5): this is what stops 47 full
    records landing in the model's context and is why the agent stays cheap over a long
    session. The full record comes from an explicit `get`.
    """

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    source: str
    source_id: str
    brand: str
    model: str
    year: int
    category: VehicleCategory
    offer_type: OfferType
    price_buy: Money | None = None
    rental_daily: Money | None = None
    mileage_km: int
    fuel_type: FuelType
    location_city: str
    available_from: date
    headline: str = Field(max_length=120, description="One line. Not the full description.")

    @classmethod
    def from_listing(cls, listing: Listing) -> Self:
        return cls(
            id=listing.id,
            source=listing.source,
            source_id=listing.source_id,
            brand=listing.brand,
            model=listing.model,
            year=listing.year,
            category=listing.category,
            offer_type=listing.offer_type,
            price_buy=listing.price_buy,
            rental_daily=listing.rental_rates.daily if listing.rental_rates else None,
            mileage_km=listing.mileage_km,
            fuel_type=listing.fuel_type,
            location_city=listing.location.city,
            available_from=listing.available_from,
            headline=_headline(listing),
        )


def _headline(listing: Listing) -> str:
    """A deterministic one-liner built from structured fields.

    Deliberately not a slice of `description`: the summary is what reaches the model most
    often, and untrusted prose does not belong in the high-frequency path.
    """
    bits = [
        f"{listing.year} {listing.brand} {listing.model} {listing.variant}",
        f"{listing.mileage_km:,} km",
        listing.fuel_type.value,
        listing.transmission.value.replace("_", " "),
    ]
    return " · ".join(bits)[:120]
