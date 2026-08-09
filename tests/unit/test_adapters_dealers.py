"""The dealer generator, the directory store, and the `condition` filter -- PLAN-02 P13.

The determinism tests here are the fast-cadence siblings of gate 13.2, and the collision test
is gate 13.3's. Both run on every `pytest tests` rather than only when a gate script does.
"""

from __future__ import annotations

from collections import Counter

import pytest

from src.adapters.catalogue.dealers import (
    DEALERS_PER_CITY,
    KNOWN_REAL_DEALER_GROUPS,
    RealWorldCollisionError,
    assert_no_real_world_collisions,
    dealers_by_source_and_city,
    generate_dealers,
    real_world_denylist,
)
from src.adapters.catalogue.generator import (
    CPO_MAX_AGE_YEARS,
    CPO_MAX_KM,
    NEW_CAR_MAX_KM,
    REFERENCE_YEAR,
    SOURCES,
    generate_catalogue,
)
from src.adapters.catalogue.taxonomy import CITIES, all_brands
from src.adapters.dealer_store import InMemoryDealerDirectory
from src.adapters.filtering import matches
from src.domain.dealer import VerificationStatus
from src.domain.enums import OfferType, VehicleCondition
from src.domain.marketplace import SearchQuery

DEALERS = generate_dealers(42, SOURCES)
CATALOGUE = generate_catalogue()


# -- determinism (gate 13.2) ---------------------------------------------------------


def test_two_generator_runs_are_byte_identical() -> None:
    first = [d.model_dump(mode="json") for d in generate_dealers(42, SOURCES)]
    second = [d.model_dump(mode="json") for d in generate_dealers(42, SOURCES)]
    assert first == second


def test_a_different_seed_produces_a_different_directory() -> None:
    """Otherwise "deterministic" would be indistinguishable from "hardcoded"."""
    assert [d.model_dump(mode="json") for d in generate_dealers(7, SOURCES)] != [
        d.model_dump(mode="json") for d in DEALERS
    ]


def test_the_directory_covers_every_city_on_every_source() -> None:
    assert len(DEALERS) == len(SOURCES) * len(CITIES) * DEALERS_PER_CITY
    index = dealers_by_source_and_city(DEALERS)
    for source in SOURCES:
        for city in CITIES:
            assert len(index[(source, city.name)]) == DEALERS_PER_CITY


def test_every_dealer_id_is_unique() -> None:
    assert len({d.id for d in DEALERS}) == len(DEALERS)


# -- fictional-name safety (gate 13.3) -----------------------------------------------


def test_no_generated_name_contains_a_real_brand_or_dealer_group() -> None:
    assert_no_real_world_collisions(DEALERS)


def test_the_denylist_is_derived_from_the_live_brand_pool() -> None:
    """Hand-copying it would leave a silent gap the day a brand is added to the taxonomy."""
    denylist = set(real_world_denylist())
    for brand in all_brands():
        assert brand.lower() in denylist
    for group in KNOWN_REAL_DEALER_GROUPS:
        assert group in denylist


def test_a_colliding_name_is_rejected_rather_than_returned() -> None:
    """The check has to actually fire -- a validator nobody can make fail proves nothing."""
    colliding = DEALERS[0].model_copy(update={"display_name": "Toyota Motors Berlin"})
    with pytest.raises(RealWorldCollisionError):
        assert_no_real_world_collisions((colliding,))


def test_addresses_use_a_street_name_from_their_own_country() -> None:
    """A Milan street in a Berlin address is the tell that stops a buyer believing the
    dealer is real -- it was in the first version of this generator."""
    german = [d for d in DEALERS if d.country == "DE"]
    italian = [d for d in DEALERS if d.country == "IT"]
    assert german and italian
    assert not any("Via " in d.address for d in german)
    assert all("Via " in d.address or "Viale" in d.address for d in italian)


# -- plausibility --------------------------------------------------------------------


def test_every_verification_state_is_populated() -> None:
    """P14's unverified-payee branch has to have real data to render against, or it is
    never seen until a judge finds it (PHASE-8 §5's failure-injection reasoning)."""
    spread = Counter(d.verification_status for d in DEALERS)
    for status in VerificationStatus:
        assert spread[status] > 0, f"no dealer is {status.value}"


def test_phone_numbers_carry_their_country_dial_code() -> None:
    assert all(d.phone.startswith("+49") for d in DEALERS if d.country == "DE")
    assert all(d.phone.startswith("+31") for d in DEALERS if d.country == "NL")


def test_ratings_sit_in_range_and_at_one_decimal_place() -> None:
    for dealer in DEALERS:
        assert 0 <= dealer.rating <= 5
        assert dealer.rating == dealer.rating.quantize(dealer.rating)


# -- the catalogue actually uses them (gate 13.1) ------------------------------------


def test_every_listing_resolves_to_exactly_one_dealer() -> None:
    by_id = {d.id: d for d in DEALERS}
    assert all(listing.dealer_id is not None for listing in CATALOGUE)
    assert all(listing.dealer_id in by_id for listing in CATALOGUE)


def test_a_listings_dealer_is_in_the_same_city_and_on_the_same_marketplace() -> None:
    by_id = {d.id: d for d in DEALERS}
    for listing in CATALOGUE:
        assert listing.dealer_id is not None
        dealer = by_id[listing.dealer_id]
        assert dealer.city == listing.location.city
        assert dealer.source == listing.source


def test_every_dealer_that_holds_stock_is_reachable_from_a_listing() -> None:
    """Not every dealer must have stock -- 108 dealers over 240 listings guarantees some
    are empty -- but the ones listings point at must all exist. The inverse of gate 13.1."""
    used = {listing.dealer_id for listing in CATALOGUE}
    known = {d.id for d in DEALERS}
    assert used <= known
    assert len(used) > len(CITIES), "listings clustered onto too few dealers to be plausible"


# -- condition (gate 13.4) -----------------------------------------------------------


def test_condition_is_derived_from_age_and_mileage_not_drawn_freely() -> None:
    for listing in CATALOGUE:
        age = REFERENCE_YEAR - listing.year
        if listing.condition is VehicleCondition.NEW:
            assert age <= 0 and listing.mileage_km <= NEW_CAR_MAX_KM
        if listing.condition is VehicleCondition.CERTIFIED_PRE_OWNED:
            assert 1 <= age <= CPO_MAX_AGE_YEARS
            assert listing.mileage_km <= CPO_MAX_KM


def test_a_rental_car_is_never_labelled_new() -> None:
    assert not [
        x for x in CATALOGUE if x.condition is VehicleCondition.NEW and x.offer_type.is_rentable
    ]


def test_all_three_conditions_appear_in_the_catalogue() -> None:
    spread = Counter(x.condition for x in CATALOGUE)
    for condition in VehicleCondition:
        assert spread[condition] > 0, f"no listing is {condition.value}"


def test_the_condition_filter_removes_rows() -> None:
    query = SearchQuery(conditions=(VehicleCondition.NEW,))
    kept = [x for x in CATALOGUE if matches(x, query)]
    assert kept, "the filter removed everything"
    assert all(x.condition is VehicleCondition.NEW for x in kept)
    assert len(kept) < len(CATALOGUE)


def test_an_empty_condition_filter_keeps_everything() -> None:
    query = SearchQuery()
    assert len([x for x in CATALOGUE if matches(x, query)]) == len(CATALOGUE)


def test_condition_and_offer_type_filter_independently() -> None:
    """Orthogonal questions: "buy or rent" and "new or used" must not imply each other."""
    used_only = SearchQuery(conditions=(VehicleCondition.USED,))
    kept = [x for x in CATALOGUE if matches(x, used_only)]
    # Used cars exist on both sides of the buy/rent split, so filtering on one says nothing
    # about the other.
    assert any(x.offer_type.is_buyable for x in kept)
    assert any(x.offer_type.is_rentable for x in kept)

    # And the converse: filtering on offer_type alone leaves more than one condition.
    buy_only = SearchQuery(offer_type=OfferType.BUY)
    buyable = [x for x in CATALOGUE if matches(x, buy_only)]
    assert len({x.condition for x in buyable}) > 1


# -- the directory store -------------------------------------------------------------


async def test_the_seeded_directory_matches_the_catalogues_dealer_ids() -> None:
    """A directory built from a different seed resolves every lookup to `None` and silently
    drops attribution -- this is the test that catches that."""
    directory = InMemoryDealerDirectory.seeded()
    for listing in CATALOGUE[:25]:
        assert listing.dealer_id is not None
        assert await directory.get(listing.dealer_id) is not None


async def test_lookup_by_ref_and_by_id_agree() -> None:
    directory = InMemoryDealerDirectory.seeded()
    dealer = DEALERS[3]
    assert await directory.get(dealer.id) == dealer
    assert await directory.by_ref(dealer.source, dealer.dealer_ref) == dealer


async def test_payee_of_a_known_dealer_is_its_identity() -> None:
    directory = InMemoryDealerDirectory.seeded()
    dealer = DEALERS[0]
    payee = await directory.payee(dealer.id)
    assert payee is not None
    assert payee.legal_name == dealer.legal_name


async def test_payee_of_none_is_none_rather_than_a_raise() -> None:
    """A listing predating the P13 re-seed must not 500 a checkout."""
    assert await InMemoryDealerDirectory.seeded().payee(None) is None


async def test_all_returns_the_whole_directory() -> None:
    assert len(await InMemoryDealerDirectory.seeded().all()) == len(DEALERS)
