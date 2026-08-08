"""Postgres store parity (gate 1.5's other half).

The in-memory store filters in Python and the Postgres store filters in SQL. Two
implementations of the same semantics drift, and the drift is invisible to any test that
exercises only one of them -- so every case here runs the *same* query through both and
demands identical ids and identical totals.

Skipped when `CARDINAL_DATABASE_URL` is unset, so `make test` stays runnable with no
container. The gate runs it with one.
"""

from __future__ import annotations

import pytest

from src.adapters.catalogue.generator import generate_catalogue
from src.adapters.db.session import dispose_engine, session_factory
from src.adapters.db.store import PostgresListingStore
from src.adapters.registry import registered_source_names
from src.adapters.store import InMemoryListingStore
from src.domain.dates import DateRange
from src.domain.enums import FuelType, OfferType, Transmission, VehicleCategory
from src.domain.marketplace import GeoPoint, SearchQuery, SortKey
from src.domain.money import Money

pytestmark = pytest.mark.postgres

BERLIN = GeoPoint(latitude=52.5200, longitude=13.4050)

QUERIES: dict[str, SearchQuery] = {
    "unfiltered": SearchQuery(),
    "category": SearchQuery(categories=(VehicleCategory.SUV, VehicleCategory.ELECTRIC)),
    "brand": SearchQuery(brands=("Toyota", "BMW", "Škoda")),
    "brand_case_insensitive": SearchQuery(brands=("toyota", "bmw")),
    "fuel": SearchQuery(fuel_types=(FuelType.ELECTRIC, FuelType.DIESEL)),
    "transmission": SearchQuery(transmissions=(Transmission.MANUAL,)),
    "offer_buy": SearchQuery(offer_type=OfferType.BUY),
    "offer_rent": SearchQuery(offer_type=OfferType.RENT),
    "offer_both": SearchQuery(offer_type=OfferType.BOTH),
    "max_price": SearchQuery(max_price=Money.of("18000")),
    "max_rental_daily": SearchQuery(max_rental_daily=Money.of("60")),
    "max_mileage": SearchQuery(max_mileage_km=40_000),
    "min_year": SearchQuery(min_year=2024),
    "min_seats": SearchQuery(min_seats=7),
    "available_between": SearchQuery(
        available_between=DateRange(start="2026-03-01", end="2026-05-31")
    ),
    "radius_tight": SearchQuery(near=BERLIN, within_km=120.0),
    "radius_wide": SearchQuery(near=BERLIN, within_km=900.0),
    "sort_price_desc": SearchQuery(sort=SortKey.PRICE_DESC),
    "sort_year_desc": SearchQuery(sort=SortKey.YEAR_DESC),
    "sort_mileage_asc": SearchQuery(sort=SortKey.MILEAGE_ASC),
    "sort_soonest": SearchQuery(sort=SortKey.AVAILABLE_SOONEST),
    "page_two": SearchQuery(page=2, page_size=13, sort=SortKey.PRICE_ASC),
    "combined": SearchQuery(
        categories=(VehicleCategory.SUV,),
        offer_type=OfferType.BUY,
        max_price=Money.of("40000"),
        min_year=2021,
        max_mileage_km=90_000,
        sort=SortKey.MILEAGE_ASC,
    ),
}


@pytest.fixture(scope="module")
def stores(database_url_or_skip: str):  # type: ignore[no-untyped-def]
    yield PostgresListingStore(session_factory()), InMemoryListingStore(generate_catalogue())


@pytest.mark.parametrize("name", sorted(QUERIES))
async def test_postgres_matches_in_memory(name: str, stores) -> None:  # type: ignore[no-untyped-def]
    postgres, memory = stores
    sources = list(registered_source_names())

    pg_items, pg_total = await postgres.query(QUERIES[name], sources=sources)
    mem_items, mem_total = await memory.query(QUERIES[name], sources=sources)

    assert pg_total == mem_total, f"{name}: totals differ"
    assert [i.id for i in pg_items] == [i.id for i in mem_items], f"{name}: ordering differs"


async def test_full_records_round_trip_through_the_database(stores) -> None:  # type: ignore[no-untyped-def]
    """Gate 1.7 against real rows: what comes back out of Postgres is what went in."""
    postgres, memory = stores
    for expected in memory.listings[:40]:
        actual = await postgres.fetch(expected.source, expected.source_id)
        assert actual == expected, f"{expected.source_id} did not survive the round trip"
        assert actual is not None and actual.raw


async def test_unknown_id_is_none_not_an_error(stores) -> None:  # type: ignore[no-untyped-def]
    postgres, _ = stores
    assert await postgres.fetch("mock_autobazaar", "nope") is None


async def test_counts_match(stores) -> None:  # type: ignore[no-untyped-def]
    postgres, memory = stores
    assert await postgres.count() == await memory.count()
    for source in registered_source_names():
        assert await postgres.count(sources=[source]) == await memory.count(sources=[source])


@pytest.fixture(scope="module", autouse=True)
def _dispose():  # type: ignore[no-untyped-def]
    yield
    import asyncio
    import sys

    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(dispose_engine())
    else:
        asyncio.run(dispose_engine())
