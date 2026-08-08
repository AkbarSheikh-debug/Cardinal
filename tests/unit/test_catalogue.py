"""Catalogue shape and realism (PHASE-1 §4).

These are the assertions behind gate 1.1-1.4 and 1.8. They live as tests as well as gate
criteria because a gate is run at the end of a phase and a test is run on every change --
and the correlation rules are exactly the thing that quietly rots.
"""

from __future__ import annotations

import statistics as st
from collections import Counter, defaultdict

import pytest

from src.adapters.catalogue.generator import (
    MIN_BRANDS_PER_CATEGORY,
    PRICE_NOISE_SIGMA,
    expected_market_value_eur,
    generate_catalogue,
)
from src.adapters.catalogue.taxonomy import brand_tier
from src.domain.enums import FuelType, OfferType, TimingMechanism, VehicleCategory
from src.domain.listing import Listing

#: Gate 1.8's threshold. The bound is arithmetic given bounded noise, so a failure here
#: means a price stopped deriving from (brand_tier, category, year, mileage).
MAX_PRICE_Z = 2.0


@pytest.fixture(scope="module")
def catalogue() -> tuple[Listing, ...]:
    return generate_catalogue()


def test_catalogue_size(catalogue: tuple[Listing, ...]) -> None:
    assert len(catalogue) == 240


def test_at_least_ten_categories(catalogue: tuple[Listing, ...]) -> None:
    assert len({item.category for item in catalogue}) >= 10


def test_at_least_ten_brands_in_every_category(catalogue: tuple[Listing, ...]) -> None:
    by_category: defaultdict[VehicleCategory, set[str]] = defaultdict(set)
    for item in catalogue:
        by_category[item.category].add(item.brand)
    thin = {c: sorted(b) for c, b in by_category.items() if len(b) < MIN_BRANDS_PER_CATEGORY}
    assert not thin, f"categories below the brand floor: {thin}"


def test_both_offer_types_are_well_represented(catalogue: tuple[Listing, ...]) -> None:
    buyable = sum(1 for item in catalogue if item.offer_type.is_buyable)
    rentable = sum(1 for item in catalogue if item.offer_type.is_rentable)
    assert buyable >= 40 and rentable >= 40, f"buy={buyable} rent={rentable}"


def test_natural_keys_are_unique(catalogue: tuple[Listing, ...]) -> None:
    duplicates = [key for key, n in Counter(i.natural_key for i in catalogue).items() if n > 1]
    assert not duplicates


def test_seed_is_deterministic() -> None:
    """Gate 1.6, in miniature: same seed, identical output."""
    first = [item.model_dump(mode="json") for item in generate_catalogue()]
    second = [item.model_dump(mode="json") for item in generate_catalogue()]
    assert first == second


def test_a_different_seed_produces_a_different_catalogue() -> None:
    """Otherwise `seed` is decorative and gate 1.6 proves nothing."""
    assert generate_catalogue(seed=42) != generate_catalogue(seed=43)


# ---------------------------------------------------------------------------
# Realism (PHASE-1 §4.1)
# ---------------------------------------------------------------------------


def test_price_derives_from_the_cohort_model(catalogue: tuple[Listing, ...]) -> None:
    """Gate 1.8 -- the criterion people skip.

    Skip it and every ranking screenshot looks broken, because a 2015 budget hatchback
    outpricing a 2024 luxury saloon makes the *ranking* look wrong rather than the data.
    """
    worst: tuple[float, str] = (0.0, "")
    for item in catalogue:
        expected = expected_market_value_eur(
            item.category, brand_tier(item.brand), item.year, item.mileage_km
        )
        z = abs(float(item.market_value.amount) / expected - 1.0) / PRICE_NOISE_SIGMA
        if z > worst[0]:
            worst = (z, f"{item.source_id} {item.year} {item.brand} {item.model}")
    assert worst[0] <= MAX_PRICE_Z, f"{worst[1]} sits {worst[0]:.2f} sigma off its cohort"


def test_price_correlates_with_the_model_across_the_catalogue(
    catalogue: tuple[Listing, ...],
) -> None:
    actual = [float(item.market_value.amount) for item in catalogue]
    expected = [
        expected_market_value_eur(i.category, brand_tier(i.brand), i.year, i.mileage_km)
        for i in catalogue
    ]
    assert st.correlation(actual, expected) >= 0.95


def test_mileage_tracks_age(catalogue: tuple[Listing, ...]) -> None:
    """~12-18k km/year, with spread. A 2024 car with 300,000 km reads as fake instantly."""
    for item in catalogue:
        age = max(2026 - item.year, 0)
        assert item.mileage_km <= max(age, 1) * 26_000 + 6_000, f"{item.source_id} too many km"


def test_no_used_car_is_priced_above_a_new_one(catalogue: tuple[Listing, ...]) -> None:
    from src.adapters.catalogue.taxonomy import CATEGORY_SHAPES, TIER_VALUE_MULTIPLIER

    for item in catalogue:
        ceiling = (
            CATEGORY_SHAPES[item.category].base_value_eur
            * TIER_VALUE_MULTIPLIER[brand_tier(item.brand)]
            * 1.10  # the price-noise band
        )
        assert float(item.market_value.amount) <= ceiling, f"{item.source_id} exceeds list price"


def test_electric_cars_have_coherent_drivetrains(catalogue: tuple[Listing, ...]) -> None:
    for item in catalogue:
        if item.fuel_type is FuelType.ELECTRIC:
            assert item.timing_mechanism is TimingMechanism.NOT_APPLICABLE
            assert item.service_interval_km is None
        else:
            assert item.timing_mechanism is not TimingMechanism.NOT_APPLICABLE
            assert item.service_interval_km is not None


def test_depreciation_reflects_brand_tier_and_category() -> None:
    """A Toyota coupe holds value; a luxury saloon does not. If that is not true in the
    data, the rent-vs-buy demo produces a plausible answer rather than a true one.
    """
    catalogue = generate_catalogue()

    def mean_five_year(category: VehicleCategory, tier_name: str) -> float:
        points = [
            item.depreciation_curve[4]
            for item in catalogue
            if item.category is category and brand_tier(item.brand).value == tier_name
        ]
        return st.fmean(points) if points else 0.0

    sports_mainstream = mean_five_year(VehicleCategory.SPORTS, "mainstream")
    luxury_luxury = mean_five_year(VehicleCategory.LUXURY, "luxury")
    assert sports_mainstream > luxury_luxury > 0


def test_rental_listings_price_nonlinearly(catalogue: tuple[Listing, ...]) -> None:
    for item in catalogue:
        if item.rental_rates is None:
            continue
        assert item.rental_rates.weekly < item.rental_rates.daily * 7
        assert item.rental_rates.monthly < item.rental_rates.weekly * 4


def test_availability_dates_cluster_rather_than_spread_uniformly(
    catalogue: tuple[Listing, ...],
) -> None:
    """Stock arrives in batches -- fleet cycles, lease returns -- not one car a day."""
    months = Counter(item.available_from.month for item in catalogue)
    busiest = max(months.values()) / len(catalogue)
    assert busiest > 1 / 12 * 1.4, f"availability looks uniform: {dict(sorted(months.items()))}"


def test_offer_mix_matches_the_plan(catalogue: tuple[Listing, ...]) -> None:
    counts = Counter(item.offer_type for item in catalogue)
    assert counts[OfferType.BUY] == 130
    assert counts[OfferType.RENT] == 90
    assert counts[OfferType.BOTH] == 20
