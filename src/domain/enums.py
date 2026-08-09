"""Closed vocabularies shared by every layer.

These are `str` enums so they serialise to readable JSON and compare equal to the plain
strings a tool schema or a database column will hand back.
"""

from __future__ import annotations

from enum import StrEnum


class Currency(StrEnum):
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    INR = "INR"


class VehicleCategory(StrEnum):
    """The twelve categories in PHASE-1 §4. The brief requires at least ten."""

    HATCHBACK = "hatchback"
    SEDAN = "sedan"
    SUV = "suv"
    CROSSOVER = "crossover"
    COUPE = "coupe"
    CONVERTIBLE = "convertible"
    PICKUP = "pickup"
    VAN_MPV = "van_mpv"
    WAGON = "wagon"
    ELECTRIC = "electric"
    LUXURY = "luxury"
    SPORTS = "sports"


class VehicleCondition(StrEnum):
    """New, used, or manufacturer-certified (PLAN-02 P13, proposal doc #2).

    Orthogonal to `OfferType`: "am I buying or renting" and "is this car new or used" are
    different questions, and a dealer selling new stock versus a lease return are different
    trust levels, financing paths, and warranty positions.

    `CERTIFIED_PRE_OWNED` is deliberately its own value rather than a flag on `USED`. It is
    the one a buyer actually shops for -- it carries a manufacturer-backed warranty that a
    private used sale does not -- and folding it into `USED` would make that undiscoverable.
    """

    NEW = "new"
    USED = "used"
    CERTIFIED_PRE_OWNED = "certified_pre_owned"

    @property
    def is_used(self) -> bool:
        """CPO counts as used: it has had an owner, whatever warranty rides along."""
        return self is not VehicleCondition.NEW

    @property
    def has_manufacturer_warranty(self) -> bool:
        return self in (VehicleCondition.NEW, VehicleCondition.CERTIFIED_PRE_OWNED)


class OfferType(StrEnum):
    BUY = "buy"
    RENT = "rent"
    BOTH = "both"

    @property
    def is_buyable(self) -> bool:
        return self in (OfferType.BUY, OfferType.BOTH)

    @property
    def is_rentable(self) -> bool:
        return self in (OfferType.RENT, OfferType.BOTH)


class FuelType(StrEnum):
    PETROL = "petrol"
    DIESEL = "diesel"
    HYBRID = "hybrid"
    PHEV = "phev"
    ELECTRIC = "electric"

    @property
    def is_electric_only(self) -> bool:
        return self is FuelType.ELECTRIC


class Transmission(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    CVT = "cvt"
    DUAL_CLUTCH = "dual_clutch"
    SINGLE_SPEED = "single_speed"


class TimingMechanism(StrEnum):
    """Why this is a first-class field: a belt is a ~€900 service event at ~100k km and a
    chain is not, and that difference is decision-relevant. P6's `PowertrainExplainer`
    renders it; P5's TCO maintenance line prices it.
    """

    BELT = "belt"
    CHAIN = "chain"
    NOT_APPLICABLE = "n-a"


class PowertrainArchetype(StrEnum):
    """The eight archetypes in PLAN-00 §6.6 / PHASE-6 §5.

    Finite and never stale: eight 3D cutaways cover every listing in the catalogue, so the
    explainer misrepresents nothing.
    """

    I3_TURBO = "i3_turbo"
    I4_NA = "i4_na"
    I4_TURBO = "i4_turbo"
    V6 = "v6"
    V8 = "v8"
    HYBRID = "hybrid"
    PHEV = "phev"
    BEV_SKATEBOARD = "bev_skateboard"


class EfficiencyUnit(StrEnum):
    """Combustion economy and EV consumption are not the same quantity, and silently
    storing both in one float is how an energy line item ends up an order of magnitude out.
    """

    L_PER_100KM = "l_per_100km"
    KWH_PER_100KM = "kwh_per_100km"


class BrandTier(StrEnum):
    """Drives price, depreciation and insurance banding in the generator (PHASE-1 §4.1)."""

    BUDGET = "budget"
    MAINSTREAM = "mainstream"
    PREMIUM = "premium"
    LUXURY = "luxury"


class MarketplaceKind(StrEnum):
    RENTAL = "rental"
    DEALER = "dealer"
