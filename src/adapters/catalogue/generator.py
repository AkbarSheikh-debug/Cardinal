"""The deterministic catalogue generator (PHASE-1 §4).

Generate, don't hand-write -- but generate *correlated*, not random. Randomly assigned
fields produce a catalogue where a 2015 Tata costs more than a 2023 Porsche, and every
ranking screenshot then looks broken. Gate 1.8 is the criterion people skip; §4.1's rules
are what make it pass.

Determinism is a hard requirement, not a nicety: gate 1.6 runs the seed twice and compares
byte for byte. That means no `datetime.now()`, no `set` iteration, and no dict keyed on
anything whose order isn't insertion order.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, NamedTuple

from src.adapters.catalogue.dealers import (
    dealers_by_source_and_city,
    generate_dealers,
)
from src.adapters.catalogue.taxonomy import (
    ALWAYS_ELECTRIC_BRANDS,
    CATEGORY_SHAPES,
    CITIES,
    MODELS_BY_CATEGORY,
    TIER_VALUE_MULTIPLIER,
    TRIMS_BY_TIER,
    ModelSpec,
    brand_tier,
    brands_in_category,
)
from src.domain.dates import DateRange
from src.domain.dealer import Dealer
from src.domain.enums import (
    BrandTier,
    Currency,
    EfficiencyUnit,
    FuelType,
    OfferType,
    PowertrainArchetype,
    TimingMechanism,
    Transmission,
    VehicleCategory,
    VehicleCondition,
)
from src.domain.listing import Efficiency, Listing, Location, RentalRates, listing_uuid
from src.domain.money import Money

# ---------------------------------------------------------------------------
# Fixed reference points. Nothing here reads the clock.
# ---------------------------------------------------------------------------

DEFAULT_SEED = 42
DEFAULT_TOTAL = 240

#: The catalogue's "now". A generated dataset that moves with the wall clock is not
#: reproducible, and gate 1.6 would be untestable.
CATALOGUE_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
REFERENCE_YEAR = 2026

#: PHASE-1 §4: 130 dealer `buy`, 90 rental `rent`, 20 `both`.
OFFER_MIX: dict[OfferType, int] = {OfferType.BUY: 130, OfferType.RENT: 90, OfferType.BOTH: 20}

#: The floor gate 1.3 asserts. The generator guarantees it by construction rather than
#: hoping a random draw covers every category.
MIN_BRANDS_PER_CATEGORY = 10

SOURCE_DEALER = "mock_autobazaar"
SOURCE_RENTAL = "mock_drivenow"

#: Both marketplaces, in a fixed order -- what the dealer directory is generated for
#: (PLAN-02 P13). A tuple, not a `set`, because gate 13.2 compares two runs byte for byte.
SOURCES: tuple[str, ...] = (SOURCE_DEALER, SOURCE_RENTAL)

#: A rental marketplace that also sells ex-fleet cars is a real business model, and it puts
#: every `both` listing on the adapter whose `availability` actually means something.
SOURCE_FOR_OFFER: dict[OfferType, str] = {
    OfferType.BUY: SOURCE_DEALER,
    OfferType.RENT: SOURCE_RENTAL,
    OfferType.BOTH: SOURCE_RENTAL,
}

SOURCE_ID_PREFIX = {SOURCE_DEALER: "AB", SOURCE_RENTAL: "DN"}

#: Bounded multiplicative noise on price. Bounded, because gate 1.8 asserts no listing sits
#: more than 2 sigma off its cohort -- an unbounded tail would fail it by construction.
PRICE_NOISE_LOW = 0.92
PRICE_NOISE_HIGH = 1.08

#: Standard deviation of a uniform distribution on [PRICE_NOISE_LOW, PRICE_NOISE_HIGH].
#:
#: Gate 1.8 measures each listing's residual against this *declared* sigma and a mean of
#: 1.0, not against its cohort's sample statistics. Sample statistics were the obvious first
#: try and they are wrong here: a cohort of four can under-estimate sigma badly enough to
#: report a 2.1-sigma outlier in a catalogue whose noise is bounded at +/-8% by
#: construction, so the criterion would fail on cohort size rather than on data quality.
#: Against the declared sigma the bound is arithmetic -- max |z| is 0.08/sigma = 1.73 -- so
#: the criterion fails only if a price stops deriving from the model, which is the thing it
#: exists to catch.
PRICE_NOISE_SIGMA = (PRICE_NOISE_HIGH - PRICE_NOISE_LOW) / (2 * math.sqrt(3))

EXPECTED_KM_PER_YEAR = 15_000


# ---------------------------------------------------------------------------
# The price model. Shared with gate 1.8 -- deliberately one function, so the gate checks
# the model the generator actually used rather than a re-derived approximation of it.
# ---------------------------------------------------------------------------


def canonical_retention(category: VehicleCategory, tier: BrandTier, age_years: float) -> float:
    """Fraction of new value retained after `age_years`, with no per-listing noise."""
    first_year = _FIRST_YEAR_RETENTION[tier] + _CATEGORY_RETENTION_ADJUST[category]
    decay = _ANNUAL_DECAY[tier] + _CATEGORY_DECAY_ADJUST[category]
    first_year = min(max(first_year, 0.50), 0.88)
    decay = min(max(decay, 0.80), 0.94)
    if age_years <= 0:
        return 1.0
    if age_years <= 1:
        return 1.0 - (1.0 - first_year) * age_years
    return first_year * (decay ** (age_years - 1))


def mileage_factor(mileage_km: int, age_years: float) -> float:
    """How far the odometer pushes value away from the age-implied figure."""
    expected = max(age_years, 0.5) * EXPECTED_KM_PER_YEAR
    ratio = mileage_km / expected
    return min(max(1.0 - 0.18 * (ratio - 1.0), 0.72), 1.16)


def expected_market_value_eur(
    category: VehicleCategory, tier: BrandTier, year: int, mileage_km: int
) -> float:
    """The noise-free price the correlation rules imply.

    PHASE-1 §4.1: `price` derives from `(brand_tier, category, year, mileage)` -- never
    independent. This function *is* that derivation, and gate 1.8 checks against it rather
    than against a re-derived approximation.
    """
    age = max(REFERENCE_YEAR - year, 0)
    base = CATEGORY_SHAPES[category].base_value_eur * TIER_VALUE_MULTIPLIER[tier]
    # Clamped at 1.0: a delivery-mileage car approaches list price but never exceeds it.
    # Without the clamp the low-mileage bonus compounds with full first-year retention and
    # the catalogue prices a nearly-new van above a brand-new one.
    condition = min(canonical_retention(category, tier, age) * mileage_factor(mileage_km, age), 1.0)
    return base * condition


_FIRST_YEAR_RETENTION: dict[BrandTier, float] = {
    BrandTier.BUDGET: 0.72,
    BrandTier.MAINSTREAM: 0.77,
    BrandTier.PREMIUM: 0.70,
    BrandTier.LUXURY: 0.63,
}

_ANNUAL_DECAY: dict[BrandTier, float] = {
    BrandTier.BUDGET: 0.855,
    BrandTier.MAINSTREAM: 0.880,
    BrandTier.PREMIUM: 0.855,
    BrandTier.LUXURY: 0.830,
}

#: A Toyota coupe holds value; a luxury saloon does not (PHASE-1 §4.1). This is the term
#: that makes the rent-vs-buy demo produce a *true* answer rather than a plausible one.
_CATEGORY_RETENTION_ADJUST: dict[VehicleCategory, float] = {
    VehicleCategory.HATCHBACK: 0.01,
    VehicleCategory.SEDAN: 0.00,
    VehicleCategory.SUV: 0.02,
    VehicleCategory.CROSSOVER: 0.01,
    VehicleCategory.COUPE: 0.03,
    VehicleCategory.CONVERTIBLE: 0.00,
    VehicleCategory.PICKUP: 0.05,
    VehicleCategory.VAN_MPV: -0.02,
    VehicleCategory.WAGON: 0.00,
    VehicleCategory.ELECTRIC: -0.05,
    VehicleCategory.LUXURY: -0.04,
    VehicleCategory.SPORTS: 0.06,
}

_CATEGORY_DECAY_ADJUST: dict[VehicleCategory, float] = {
    VehicleCategory.HATCHBACK: 0.005,
    VehicleCategory.SEDAN: 0.000,
    VehicleCategory.SUV: 0.005,
    VehicleCategory.CROSSOVER: 0.005,
    VehicleCategory.COUPE: 0.015,
    VehicleCategory.CONVERTIBLE: 0.010,
    VehicleCategory.PICKUP: 0.020,
    VehicleCategory.VAN_MPV: -0.010,
    VehicleCategory.WAGON: 0.000,
    VehicleCategory.ELECTRIC: -0.020,
    VehicleCategory.LUXURY: -0.015,
    VehicleCategory.SPORTS: 0.020,
}


# ---------------------------------------------------------------------------
# Per-field derivations
# ---------------------------------------------------------------------------


def _pick_fuel(
    category: VehicleCategory, brand: str, spec: ModelSpec, rng: random.Random
) -> FuelType:
    if category is VehicleCategory.ELECTRIC or brand in ALWAYS_ELECTRIC_BRANDS:
        return FuelType.ELECTRIC
    if spec.fuel is not None:
        return spec.fuel
    mix = CATEGORY_SHAPES[category].fuel_mix
    return rng.choices(
        [FuelType.PETROL, FuelType.DIESEL, FuelType.HYBRID, FuelType.PHEV], weights=list(mix)
    )[0]


def _pick_archetype(
    fuel: FuelType,
    category: VehicleCategory,
    tier: BrandTier,
    spec: ModelSpec,
    rng: random.Random,
) -> PowertrainArchetype:
    # Electrification wins over the per-model annotation: a hybrid Multivan is a HYBRID
    # archetype whatever its combustion sibling runs.
    if fuel is FuelType.ELECTRIC:
        return PowertrainArchetype.BEV_SKATEBOARD
    if fuel is FuelType.HYBRID:
        return PowertrainArchetype.HYBRID
    if fuel is FuelType.PHEV:
        return PowertrainArchetype.PHEV

    # The model knows better than the category default whenever it says so.
    if spec.archetype is not None:
        return spec.archetype

    big = (VehicleCategory.LUXURY, VehicleCategory.SPORTS)
    if category in big and tier in (BrandTier.LUXURY, BrandTier.PREMIUM):
        return rng.choices(
            [PowertrainArchetype.V8, PowertrainArchetype.V6, PowertrainArchetype.I4_TURBO],
            weights=[0.45, 0.35, 0.20],
        )[0]
    if category in big:
        return rng.choices(
            [PowertrainArchetype.V6, PowertrainArchetype.I4_TURBO], weights=[0.4, 0.6]
        )[0]
    if category in (VehicleCategory.PICKUP, VehicleCategory.VAN_MPV):
        return rng.choices(
            [PowertrainArchetype.V6, PowertrainArchetype.I4_TURBO], weights=[0.35, 0.65]
        )[0]
    if category in (VehicleCategory.COUPE, VehicleCategory.CONVERTIBLE):
        return rng.choices(
            [PowertrainArchetype.V6, PowertrainArchetype.I4_TURBO, PowertrainArchetype.I4_NA],
            weights=[0.25, 0.55, 0.20],
        )[0]
    if category is VehicleCategory.HATCHBACK:
        return rng.choices(
            [PowertrainArchetype.I3_TURBO, PowertrainArchetype.I4_NA, PowertrainArchetype.I4_TURBO],
            weights=[0.40, 0.35, 0.25],
        )[0]
    return rng.choices(
        [PowertrainArchetype.I4_TURBO, PowertrainArchetype.I4_NA], weights=[0.6, 0.4]
    )[0]


def _pick_timing(
    fuel: FuelType, archetype: PowertrainArchetype, tier: BrandTier, rng: random.Random
) -> TimingMechanism:
    if fuel is FuelType.ELECTRIC:
        return TimingMechanism.NOT_APPLICABLE
    chance = 0.35
    if tier in (BrandTier.PREMIUM, BrandTier.LUXURY):
        chance += 0.25
    if archetype in (PowertrainArchetype.V6, PowertrainArchetype.V8):
        chance += 0.15
    if archetype in (PowertrainArchetype.HYBRID, PowertrainArchetype.PHEV):
        chance += 0.10
    return TimingMechanism.CHAIN if rng.random() < chance else TimingMechanism.BELT


def _pick_service_interval(fuel: FuelType, tier: BrandTier, rng: random.Random) -> int | None:
    if fuel is FuelType.ELECTRIC:
        return None
    base = {
        FuelType.PETROL: 15_000,
        FuelType.DIESEL: 20_000,
        FuelType.HYBRID: 15_000,
        FuelType.PHEV: 15_000,
    }[fuel]
    if tier in (BrandTier.PREMIUM, BrandTier.LUXURY):
        base += rng.choice([0, 5_000, 10_000])
    return base


def _pick_insurance_band(
    category: VehicleCategory, tier: BrandTier, fuel: FuelType, rng: random.Random
) -> int:
    base = {
        VehicleCategory.HATCHBACK: 5,
        VehicleCategory.SEDAN: 11,
        VehicleCategory.SUV: 14,
        VehicleCategory.CROSSOVER: 10,
        VehicleCategory.COUPE: 16,
        VehicleCategory.CONVERTIBLE: 17,
        VehicleCategory.PICKUP: 13,
        VehicleCategory.VAN_MPV: 12,
        VehicleCategory.WAGON: 11,
        VehicleCategory.ELECTRIC: 13,
        VehicleCategory.LUXURY: 18,
        VehicleCategory.SPORTS: 19,
    }[category]
    base += {
        BrandTier.BUDGET: -2,
        BrandTier.MAINSTREAM: 0,
        BrandTier.PREMIUM: 2,
        BrandTier.LUXURY: 3,
    }[tier]
    if fuel is FuelType.ELECTRIC:
        # PHASE-1 §4.1: EVs band differently. Battery-pack repair costs push them up.
        base += 1
    return min(max(base + rng.choice([-1, 0, 0, 1]), 1), 20)


def _pick_transmission(
    fuel: FuelType, category: VehicleCategory, tier: BrandTier, rng: random.Random
) -> Transmission:
    if fuel is FuelType.ELECTRIC:
        return Transmission.SINGLE_SPEED
    if fuel is FuelType.HYBRID:
        return Transmission.CVT
    if tier in (BrandTier.PREMIUM, BrandTier.LUXURY):
        return rng.choices([Transmission.AUTOMATIC, Transmission.DUAL_CLUTCH], weights=[0.6, 0.4])[
            0
        ]
    if category in (VehicleCategory.HATCHBACK, VehicleCategory.CROSSOVER):
        return rng.choices([Transmission.MANUAL, Transmission.AUTOMATIC], weights=[0.55, 0.45])[0]
    return rng.choices([Transmission.MANUAL, Transmission.AUTOMATIC], weights=[0.35, 0.65])[0]


def _pick_efficiency(
    fuel: FuelType, category: VehicleCategory, archetype: PowertrainArchetype, rng: random.Random
) -> Efficiency:
    heavy = category in (
        VehicleCategory.SUV,
        VehicleCategory.PICKUP,
        VehicleCategory.VAN_MPV,
        VehicleCategory.LUXURY,
        VehicleCategory.SPORTS,
    )
    if fuel is FuelType.ELECTRIC:
        low, high = (19.0, 24.5) if heavy else (14.0, 19.0)
        unit = EfficiencyUnit.KWH_PER_100KM
    elif fuel is FuelType.PHEV:
        low, high = (2.0, 3.6)
        unit = EfficiencyUnit.L_PER_100KM
    elif fuel is FuelType.HYBRID:
        low, high = (4.0, 6.2)
        unit = EfficiencyUnit.L_PER_100KM
    elif fuel is FuelType.DIESEL:
        low, high = (5.6, 9.0) if heavy else (4.4, 6.4)
        unit = EfficiencyUnit.L_PER_100KM
    else:
        low, high = (8.5, 13.5) if heavy else (5.4, 8.6)
        if archetype is PowertrainArchetype.V8:
            low, high = (11.0, 15.5)
        unit = EfficiencyUnit.L_PER_100KM
    value = Decimal(str(round(rng.uniform(low, high), 1)))
    return Efficiency(value=value, unit=unit)


#: Delivery mileage. Above this a zero-age car is a demonstrator or a pre-registration, which
#: is `USED` in every way a buyer cares about even though the plate is this year's.
NEW_CAR_MAX_KM = 1_500

#: Manufacturer certified-pre-owned programmes have an age and a mileage ceiling. These are
#: the illustrative ones this catalogue uses; like everything in `src/domain/constants.py`
#: they are representative rather than sourced from any specific programme.
CPO_MAX_AGE_YEARS = 5
CPO_MAX_KM = 80_000

#: How often an eligible car is actually certified, by tier. Premium and luxury brands run
#: the biggest CPO programmes -- that is what the warranty is worth defending on a used sale.
_CPO_RATE: dict[BrandTier, float] = {
    BrandTier.BUDGET: 0.10,
    BrandTier.MAINSTREAM: 0.22,
    BrandTier.PREMIUM: 0.42,
    BrandTier.LUXURY: 0.50,
}


def _pick_condition(
    year: int, mileage_km: int, tier: BrandTier, offer_type: OfferType, rng: random.Random
) -> VehicleCondition:
    """Derived from age, mileage and tier -- never drawn independently.

    Same discipline as every other field here (PHASE-1 §4.1): a randomly-assigned `condition`
    would produce a 2019 car with 140,000 km labelled `NEW`, and one screenshot of that makes
    the whole catalogue look fabricated.

    A rental car is never `NEW`: it is in a rental fleet, which means it has been driven by
    someone other than the buyer, whatever its odometer says.
    """
    age = REFERENCE_YEAR - year
    if age <= 0 and mileage_km <= NEW_CAR_MAX_KM and not offer_type.is_rentable:
        return VehicleCondition.NEW
    eligible = 1 <= age <= CPO_MAX_AGE_YEARS and mileage_km <= CPO_MAX_KM
    if eligible and rng.random() < _CPO_RATE[tier]:
        return VehicleCondition.CERTIFIED_PRE_OWNED
    return VehicleCondition.USED


def _pick_year_and_mileage(category: VehicleCategory, rng: random.Random) -> tuple[int, int]:
    # Weighted toward recent stock -- a forecourt is not a uniform sample of the last decade.
    years = list(range(REFERENCE_YEAR - 9, REFERENCE_YEAR + 1))
    weights = [0.03, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.15, 0.12]
    year = rng.choices(years, weights=weights)[0]
    age = REFERENCE_YEAR - year
    if age == 0:
        mileage = int(rng.uniform(50, 4_000))
    else:
        per_year = rng.uniform(11_000, 18_500)
        mileage = int(age * per_year + rng.uniform(-2_000, 3_500))
    if category is VehicleCategory.SPORTS:
        mileage = int(mileage * rng.uniform(0.45, 0.75))  # weekend cars do fewer miles
    return year, max(mileage - mileage % 100, 0)


def _depreciation_curve(
    category: VehicleCategory, tier: BrandTier, rng: random.Random
) -> tuple[float, float, float, float, float]:
    first = canonical_retention(category, tier, 1.0) + rng.uniform(-0.02, 0.02)
    decay = _ANNUAL_DECAY[tier] + _CATEGORY_DECAY_ADJUST[category] + rng.uniform(-0.01, 0.01)
    first = min(max(first, 0.50), 0.88)
    decay = min(max(decay, 0.80), 0.94)
    points = [round(first * decay**step, 4) for step in range(5)]
    return (points[0], points[1], points[2], points[3], points[4])


#: Stock does not arrive uniformly across a year. It arrives in batches -- fleet cycles,
#: lease returns, registration plate changes.
_AVAILABILITY_ANCHORS: tuple[tuple[date, float], ...] = (
    (date(2026, 1, 6), 0.14),
    (date(2026, 2, 2), 0.10),
    (date(2026, 3, 2), 0.16),
    (date(2026, 4, 1), 0.12),
    (date(2026, 5, 4), 0.08),
    (date(2026, 6, 1), 0.09),
    (date(2026, 7, 1), 0.07),
    (date(2026, 9, 1), 0.12),
    (date(2026, 10, 1), 0.07),
    (date(2026, 11, 2), 0.05),
)


def _pick_available_from(rng: random.Random) -> date:
    anchors = [a for a, _ in _AVAILABILITY_ANCHORS]
    weights = [w for _, w in _AVAILABILITY_ANCHORS]
    anchor = rng.choices(anchors, weights=weights)[0]
    return anchor + timedelta(days=rng.randint(0, 9))


def _blocked_windows(available_from: date, rng: random.Random) -> tuple[DateRange, ...]:
    """Existing bookings on a rental car. Stored in `raw`, read back by the rental adapter.

    Keeping them in the raw payload rather than on `Listing` is deliberate: a dealer feed
    has no such concept, and `Listing` is the shape *every* adapter normalises to.
    """
    windows: list[DateRange] = []
    cursor = available_from + timedelta(days=rng.randint(3, 25))
    for _ in range(rng.randint(0, 3)):
        length = rng.randint(2, 9)
        window = DateRange(start=cursor, end=cursor + timedelta(days=length))
        if window.end.year > 2026:
            break
        windows.append(window)
        cursor = window.end + timedelta(days=rng.randint(6, 40))
    return tuple(windows)


def _money_eur(value: float) -> Money:
    return Money(
        amount=Decimal(str(round(value, 2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        currency=Currency.EUR,
    )


def _rental_rates(market_value: Money, rng: random.Random) -> RentalRates:
    """Rental pricing is nonlinear (PHASE-5 §5): weekly is not daily x 7."""
    daily_value = max(float(market_value.amount) * 0.0016 + 18.0, 22.0) * rng.uniform(0.92, 1.10)
    daily = _money_eur(daily_value)
    weekly = _money_eur(daily_value * rng.uniform(5.2, 5.9))
    monthly = _money_eur(float(weekly.amount) * rng.uniform(3.0, 3.5))
    return RentalRates(
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        included_km_per_day=rng.choice([100, 150, 200, 250]),
        excess_km_rate=_money_eur(rng.uniform(0.16, 0.38)),
        insurance_included=rng.random() < 0.55,
    )


def _description(
    spec: ModelSpec,
    variant: str,
    year: int,
    mileage_km: int,
    fuel: FuelType,
    city: str,
    timing: TimingMechanism,
    rng: random.Random,
) -> str:
    """Composed from structured facts.

    This text is treated as untrusted third-party prose everywhere downstream
    (CONSTITUTION I.4) even though we generated it -- the moment a real adapter lands, the
    handling has to already be right.
    """
    openers = (
        "Well-kept example with a full service history.",
        "One previous owner, documented maintenance throughout.",
        "Recent major service completed; MOT/TÜV fresh.",
        "Ex-lease vehicle, workshop-inspected before listing.",
        "Careful private ownership, garage-kept.",
    )
    closers = {
        TimingMechanism.BELT: "Cambelt replaced within the last service interval.",
        TimingMechanism.CHAIN: "Timing chain, no belt-change interval to budget for.",
        TimingMechanism.NOT_APPLICABLE: "Battery health checked at handover.",
    }
    return (
        f"{rng.choice(openers)} {year} {spec.brand} {spec.model} {variant} in {city}, "
        f"{mileage_km:,} km, {fuel.value}. {closers[timing]}"
    )


def _raw_payload(
    spec: ModelSpec,
    source: str,
    source_id: str,
    year: int,
    mileage_km: int,
    market_value: Money,
    blocked: tuple[DateRange, ...],
) -> dict[str, Any]:
    """A plausible upstream payload in the marketplace's *own* field names.

    `Listing.raw` is retained so that when a field turns out to be mapped wrong, historical
    rows can be re-normalised instead of re-fetched (PHASE-0 §4). Keeping the names
    deliberately un-canonical is what makes that exercise meaningful.
    """
    return {
        "feed": source,
        "listingRef": source_id,
        "make": spec.brand,
        "modelName": spec.model,
        "firstRegistration": f"{year}-03-01",
        "odometer": {"value": mileage_km, "unit": "km"},
        "valuationMinor": int(market_value.amount * 100),
        "currency": market_value.currency.value,
        "blockedWindows": [{"from": w.start.isoformat(), "to": w.end.isoformat()} for w in blocked],
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _category_plan(total: int, rng: random.Random) -> list[tuple[VehicleCategory, str | None]]:
    """Decide the (category, required-brand) slot for every listing.

    The first `12 x MIN_BRANDS_PER_CATEGORY` slots pin a specific brand so that gate 1.3's
    ten-brands-in-every-category floor holds by construction. Hoping a random draw covers
    it is how that criterion fails at 2am.
    """
    categories = list(VehicleCategory)
    plan: list[tuple[VehicleCategory, str | None]] = []

    for category in categories:
        eligible = list(brands_in_category(category))
        if len(eligible) < MIN_BRANDS_PER_CATEGORY:
            raise ValueError(
                f"{category} has only {len(eligible)} eligible brands; "
                f"gate 1.3 needs at least {MIN_BRANDS_PER_CATEGORY}"
            )
        rng.shuffle(eligible)
        for brand in eligible[:MIN_BRANDS_PER_CATEGORY]:
            plan.append((category, brand))

    remaining = total - len(plan)
    if remaining < 0:
        raise ValueError(
            f"total={total} cannot satisfy {MIN_BRANDS_PER_CATEGORY} brands "
            f"across {len(categories)} categories"
        )
    for _ in range(remaining):
        plan.append((rng.choice(categories), None))

    rng.shuffle(plan)
    return plan


def _offer_types(total: int, rng: random.Random) -> list[OfferType]:
    mix: list[OfferType] = []
    for offer_type, count in OFFER_MIX.items():
        mix.extend([offer_type] * count)
    if len(mix) != total:
        # Scale the mix proportionally when a caller asks for a non-default total.
        mix = []
        for offer_type, count in OFFER_MIX.items():
            mix.extend([offer_type] * round(count * total / DEFAULT_TOTAL))
        while len(mix) < total:
            mix.append(OfferType.BUY)
        mix = mix[:total]
    rng.shuffle(mix)
    return mix


class _Draft(NamedTuple):
    """One planned listing, before it is assigned a source and an id."""

    category: VehicleCategory
    spec: ModelSpec
    offer_type: OfferType


def generate_catalogue(seed: int = DEFAULT_SEED, total: int = DEFAULT_TOTAL) -> tuple[Listing, ...]:
    """Build the whole catalogue. Same seed in, byte-identical catalogue out (gate 1.6)."""
    rng = random.Random(seed)
    plan = _category_plan(total, rng)
    offers = _offer_types(total, rng)

    drafts: list[_Draft] = []
    for (category, required_brand), offer_type in zip(plan, offers, strict=True):
        pool = MODELS_BY_CATEGORY[category]
        if required_brand is not None:
            pool = tuple(s for s in pool if s.brand == required_brand)
        drafts.append(_Draft(category, rng.choice(pool), offer_type))

    # PLAN-02 P13: the dealer directory is generated from its own `random.Random(seed)`
    # inside `generate_dealers`, so adding it here does not perturb the listing stream this
    # `rng` produces -- gate 1.8's price correlations and gate 1.3's brand spread are
    # unchanged by dealers existing.
    dealer_index = dealers_by_source_and_city(generate_dealers(seed, SOURCES))

    # Number source ids per source, in plan order, so they are stable across runs.
    counters = {SOURCE_DEALER: 1000, SOURCE_RENTAL: 1000}
    listings: list[Listing] = []
    for draft in drafts:
        source = SOURCE_FOR_OFFER[draft.offer_type]
        counters[source] += 1
        source_id = f"{SOURCE_ID_PREFIX[source]}-{counters[source]}"
        listings.append(
            _build_listing(
                source,
                source_id,
                draft.category,
                draft.spec,
                draft.offer_type,
                rng,
                dealer_index,
            )
        )

    return tuple(listings)


def _build_listing(
    source: str,
    source_id: str,
    category: VehicleCategory,
    spec: ModelSpec,
    offer_type: OfferType,
    rng: random.Random,
    dealer_index: dict[tuple[str, str], tuple[Dealer, ...]],
) -> Listing:
    tier = brand_tier(spec.brand)
    shape = CATEGORY_SHAPES[category]

    fuel = _pick_fuel(category, spec.brand, spec, rng)
    archetype = _pick_archetype(fuel, category, tier, spec, rng)
    timing = _pick_timing(fuel, archetype, tier, rng)
    year, mileage_km = _pick_year_and_mileage(category, rng)

    # -- the correlated price. See expected_market_value_eur; the only stochastic term is
    # a bounded multiplier, which is what lets gate 1.8 be a real assertion.
    expected = expected_market_value_eur(category, tier, year, mileage_km)
    market_value = _money_eur(expected * rng.uniform(PRICE_NOISE_LOW, PRICE_NOISE_HIGH))

    price_buy = None
    if offer_type.is_buyable:
        price_buy = _money_eur(float(market_value.amount) * rng.uniform(1.03, 1.09))

    rental_rates = _rental_rates(market_value, rng) if offer_type.is_rentable else None

    city = rng.choice(CITIES)
    available_from = _pick_available_from(rng)
    blocked = _blocked_windows(available_from, rng) if offer_type.is_rentable else ()
    variant = rng.choice(TRIMS_BY_TIER[tier])

    # PLAN-02 P13's two new fields draw from their **own** per-listing stream, not from
    # `rng`. Drawing from `rng` was the first version and it silently rewrote the catalogue:
    # two extra draws per listing shifted every subsequent one, so adding a `dealer_id`
    # changed which *cars* the generator produced, and
    # `test_every_car_the_demo_script_surfaces_has_its_own_model` went red because thirteen
    # models with no hand-built 3D asset had wandered into the demo's results.
    #
    # Seeding on the natural key keeps this deterministic (gates 1.6/13.2 still compare two
    # runs byte for byte) while leaving every pre-P13 field bit-identical -- which is what
    # makes gate 1.8's price correlations and gate 5.4's golden set still mean what they
    # meant before this phase. A new field must not retroactively change an old one.
    aux = random.Random(f"p13:{source}:{source_id}")

    # A dealer in the car's own city, on the car's own marketplace. A buyer told the car is
    # in Lyon and the dealer is in Warsaw has been given two facts that contradict each
    # other, and the second is the one they would act on.
    dealer = aux.choice(dealer_index[(source, city.name)])
    condition = _pick_condition(year, mileage_km, tier, offer_type, aux)

    return Listing(
        id=listing_uuid(source, source_id),
        source=source,
        source_id=source_id,
        fetched_at=CATALOGUE_EPOCH,
        raw=_raw_payload(spec, source, source_id, year, mileage_km, market_value, blocked),
        dealer_id=dealer.id,
        brand=spec.brand,
        model=spec.model,
        variant=variant,
        year=year,
        category=category,
        condition=condition,
        offer_type=offer_type,
        market_value=market_value,
        price_buy=price_buy,
        rental_rates=rental_rates,
        mileage_km=mileage_km,
        fuel_type=fuel,
        transmission=_pick_transmission(fuel, category, tier, rng),
        seats=spec.seats or shape.seats,
        doors=shape.doors,
        efficiency=_pick_efficiency(fuel, category, archetype, rng),
        depreciation_curve=_depreciation_curve(category, tier, rng),
        insurance_band=_pick_insurance_band(category, tier, fuel, rng),
        service_interval_km=_pick_service_interval(fuel, tier, rng),
        timing_mechanism=timing,
        powertrain_archetype=archetype,
        location=Location(
            city=city.name,
            country=city.country,
            latitude=city.latitude,
            longitude=city.longitude,
        ),
        available_from=available_from,
        description=_description(spec, variant, year, mileage_km, fuel, city.name, timing, rng),
    )
