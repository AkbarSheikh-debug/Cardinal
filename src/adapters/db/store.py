"""`PostgresListingStore` -- the same retrieval semantics as `InMemoryListingStore`, in SQL.

Every filter in `src/adapters/filtering.py` has a counterpart here. The two are written
independently and are kept honest by the contract suite running against both, because a
filter that means one thing in Python and another in SQL is a bug no unit test in either
implementation can see.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Float, Select, UnaryExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.mapping import to_listing
from src.adapters.db.models import ListingRow
from src.domain.enums import OfferType
from src.domain.listing import Listing
from src.domain.marketplace import SearchQuery, SortKey

#: Degrees of latitude per kilometre, for the bounding box that pre-filters a radius search.
_KM_PER_DEGREE_LAT = 110.574


class PostgresListingStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def query(
        self, q: SearchQuery, *, sources: Sequence[str]
    ) -> tuple[tuple[Listing, ...], int]:
        conditions = _conditions(q, sources)

        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(ListingRow).where(*conditions)
            )
            stmt: Select[tuple[ListingRow]] = (
                select(ListingRow)
                .where(*conditions)
                .order_by(*_order_by(q.sort))
                .offset(q.offset)
                .limit(q.page_size)
            )
            rows = (await session.scalars(stmt)).all()

        return tuple(to_listing(row) for row in rows), int(total or 0)

    async def fetch(self, source: str, source_id: str) -> Listing | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ListingRow).where(
                    ListingRow.source == source, ListingRow.source_id == source_id
                )
            )
        return to_listing(row) if row is not None else None

    async def count(self, *, sources: Sequence[str] | None = None) -> int:
        stmt = select(func.count()).select_from(ListingRow)
        if sources is not None:
            stmt = stmt.where(ListingRow.source.in_(list(sources)))
        async with self._sessions() as session:
            return int(await session.scalar(stmt) or 0)


def _conditions(q: SearchQuery, sources: Sequence[str]) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [ListingRow.source.in_(list(sources))]

    if not q.include_withdrawn:
        conditions.append(ListingRow.withdrawn_at.is_(None))

    if q.categories:
        conditions.append(ListingRow.category.in_([c.value for c in q.categories]))

    if q.brands:
        # Case-insensitive, matching the Python predicate.
        conditions.append(func.lower(ListingRow.brand).in_([b.casefold() for b in q.brands]))

    if q.conditions:
        conditions.append(ListingRow.condition.in_([c.value for c in q.conditions]))

    if q.fuel_types:
        conditions.append(ListingRow.fuel_type.in_([f.value for f in q.fuel_types]))

    if q.transmissions:
        conditions.append(ListingRow.transmission.in_([t.value for t in q.transmissions]))

    if q.offer_type is not None:
        if q.offer_type is OfferType.BUY:
            wanted = [OfferType.BUY.value, OfferType.BOTH.value]
        elif q.offer_type is OfferType.RENT:
            wanted = [OfferType.RENT.value, OfferType.BOTH.value]
        else:
            wanted = [OfferType.BOTH.value]
        conditions.append(ListingRow.offer_type.in_(wanted))

    if q.max_price is not None:
        conditions.append(ListingRow.price_buy_amount.is_not(None))
        conditions.append(ListingRow.price_buy_amount <= q.max_price.amount)

    if q.max_rental_daily is not None:
        conditions.append(ListingRow.rental_daily_amount.is_not(None))
        conditions.append(ListingRow.rental_daily_amount <= q.max_rental_daily.amount)

    if q.max_mileage_km is not None:
        conditions.append(ListingRow.mileage_km <= q.max_mileage_km)

    if q.min_year is not None:
        conditions.append(ListingRow.year >= q.min_year)

    if q.min_seats is not None:
        conditions.append(ListingRow.seats >= q.min_seats)

    if q.available_between is not None:
        conditions.append(ListingRow.available_from <= q.available_between.end)

    if q.near is not None and q.within_km is not None:
        # Two predicates, both needed. The bounding box is indexable and cuts the scan; the
        # great-circle expression is exact. Filtering by box alone would over-select at the
        # corners, and refining in Python afterwards would make `total` a count of the
        # current page rather than of the whole result set -- so the exact cut has to
        # happen in SQL, where COUNT and LIMIT/OFFSET both see it.
        lat_delta = q.within_km / _KM_PER_DEGREE_LAT
        cos_lat = max(math.cos(math.radians(q.near.latitude)), 0.01)
        lon_delta = q.within_km / (_KM_PER_DEGREE_LAT * cos_lat)
        conditions.append(
            ListingRow.latitude.between(
                Decimal(str(q.near.latitude - lat_delta)), Decimal(str(q.near.latitude + lat_delta))
            )
        )
        conditions.append(
            ListingRow.longitude.between(
                Decimal(str(q.near.longitude - lon_delta)),
                Decimal(str(q.near.longitude + lon_delta)),
            )
        )
        conditions.append(_great_circle_km(q.near.latitude, q.near.longitude) <= q.within_km)

    return conditions


def _great_circle_km(latitude: float, longitude: float) -> ColumnElement[float]:
    """Haversine in plain SQL -- no PostGIS, so the container stays one image.

    Mirrors `GeoPoint.distance_km` exactly; the contract suite compares the two stores'
    results for the same radius query.
    """
    earth_radius_km = 6371.0088
    row_lat = func.radians(ListingRow.latitude.cast(Float))
    row_lon = func.radians(ListingRow.longitude.cast(Float))
    origin_lat = math.radians(latitude)
    origin_lon = math.radians(longitude)

    half_dlat = (row_lat - origin_lat) / 2
    half_dlon = (row_lon - origin_lon) / 2
    haversine = func.power(func.sin(half_dlat), 2) + math.cos(origin_lat) * func.cos(
        row_lat
    ) * func.power(func.sin(half_dlon), 2)
    return 2 * earth_radius_km * func.asin(func.sqrt(haversine))


def _order_by(sort: SortKey) -> tuple[UnaryExpression[Any], ...]:
    """Always tie-broken on `id`, so pagination cannot repeat or skip a row."""
    match sort:
        case SortKey.PRICE_ASC:
            return (ListingRow.market_value_amount.asc(), ListingRow.id.asc())
        case SortKey.PRICE_DESC:
            return (ListingRow.market_value_amount.desc(), ListingRow.id.asc())
        case SortKey.YEAR_DESC:
            return (ListingRow.year.desc(), ListingRow.id.asc())
        case SortKey.MILEAGE_ASC:
            return (ListingRow.mileage_km.asc(), ListingRow.id.asc())
        case SortKey.AVAILABLE_SOONEST:
            return (ListingRow.available_from.asc(), ListingRow.id.asc())
