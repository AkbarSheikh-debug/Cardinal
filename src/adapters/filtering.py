"""Retrieval semantics, defined once.

The in-memory store evaluates these predicates in Python and the Postgres store expresses
the same rules in SQL. That duplication is unavoidable -- and it is exactly why the adapter
contract suite runs against both. A filter that means one thing in Python and another in
SQL is the bug this module exists to make visible.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.domain.enums import OfferType
from src.domain.listing import Listing
from src.domain.marketplace import GeoPoint, SearchQuery, SortKey


def matches(listing: Listing, q: SearchQuery) -> bool:
    """Whether one listing satisfies every filter in the query."""
    if not q.include_withdrawn and listing.withdrawn_at is not None:
        return False

    if q.categories and listing.category not in q.categories:
        return False

    if q.brands:
        wanted = {b.casefold() for b in q.brands}
        if listing.brand.casefold() not in wanted:
            return False

    if q.fuel_types and listing.fuel_type not in q.fuel_types:
        return False

    if q.transmissions and listing.transmission not in q.transmissions:
        return False

    if q.offer_type is not None and not _offer_type_matches(listing.offer_type, q.offer_type):
        return False

    if q.max_price is not None:
        # A max_price filter is a buyer's filter, so a rent-only listing is not a match --
        # not "a match with a missing price".
        if listing.price_buy is None or listing.price_buy > q.max_price:
            return False

    if q.max_rental_daily is not None:
        if listing.rental_rates is None or listing.rental_rates.daily > q.max_rental_daily:
            return False

    if q.max_mileage_km is not None and listing.mileage_km > q.max_mileage_km:
        return False

    if q.min_year is not None and listing.year < q.min_year:
        return False

    if q.min_seats is not None and listing.seats < q.min_seats:
        return False

    if q.available_between is not None:
        # "Becomes available at some point on or before the end of my window." Whether a
        # rental is actually free on specific days is `availability`'s question, not a
        # filter's -- a search that silently applied booking state would be unexplainable.
        if listing.available_from > q.available_between.end:
            return False

    if q.near is not None and q.within_km is not None:
        here = GeoPoint(latitude=listing.location.latitude, longitude=listing.location.longitude)
        if here.distance_km(q.near) > q.within_km:
            return False

    return True


def _offer_type_matches(listing_offer: OfferType, wanted: OfferType) -> bool:
    """`buy` matches buy-only and both; `rent` matches rent-only and both.

    Asking for `buy` and being shown only the buy-only rows would hide the 20 listings a
    user could actually buy, which is the opposite of useful.
    """
    if wanted is OfferType.BUY:
        return listing_offer.is_buyable
    if wanted is OfferType.RENT:
        return listing_offer.is_rentable
    return listing_offer is OfferType.BOTH


def sort_listings(listings: Iterable[Listing], sort: SortKey) -> list[Listing]:
    """Total order, always tie-broken on `id`.

    Never insertion order (CONSTITUTION II.2). Without the tie-break, two listings with the
    same price can swap between calls and page 2 then repeats or skips a row -- which is
    the pagination-stability criterion in the contract suite.
    """
    items = list(listings)

    def price_key(listing: Listing) -> float:
        # market_value, not price_buy: it is present on every listing including rent-only
        # ones, so a mixed result set gets one coherent ordering instead of two. It also
        # tracks price_buy closely, since asking price is a bounded markup on it.
        return float(listing.market_value.amount)

    match sort:
        case SortKey.PRICE_ASC:
            items.sort(key=lambda item: (price_key(item), item.id))
        case SortKey.PRICE_DESC:
            items.sort(key=lambda item: (-price_key(item), item.id))
        case SortKey.YEAR_DESC:
            items.sort(key=lambda item: (-item.year, item.id))
        case SortKey.MILEAGE_ASC:
            items.sort(key=lambda item: (item.mileage_km, item.id))
        case SortKey.AVAILABLE_SOONEST:
            items.sort(key=lambda item: (item.available_from, item.id))
    return items


def paginate(listings: list[Listing], q: SearchQuery) -> tuple[list[Listing], int]:
    total = len(listings)
    return listings[q.offset : q.offset + q.page_size], total
