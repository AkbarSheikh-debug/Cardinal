"""The adapter contract suite (PHASE-1 §3, gate 1.5).

One parametrised suite, run against *every* registered adapter. This is the file that makes
adding a real marketplace a two-hour job instead of a two-week one: implement the protocol,
register it, and this suite tells you precisely where the normalisation is wrong.

Nothing in here may reference `MockDriveNow` or `MockAutoBazaar` by name. Behaviour that
legitimately differs between a rental and a dealer marketplace is selected on
`adapter.kind`, never on the adapter's identity -- a test that special-cases one
implementation has stopped testing the contract.
"""

from __future__ import annotations

import pytest

from src.adapters.protocol import (
    ListingNotFoundError,
    MarketplaceAdapter,
    QuoteNotAvailableError,
)
from src.domain.dates import DateRange
from src.domain.enums import MarketplaceKind, OfferType
from src.domain.listing import Listing
from src.domain.marketplace import (
    MAX_SUMMARY_TOKENS,
    AvailabilityStatus,
    QuoteTerms,
    SearchQuery,
    SortKey,
    summary_token_estimate,
)

WINDOW = DateRange(start="2026-04-06", end="2026-04-16")


async def _first_listing(adapter: MarketplaceAdapter) -> Listing:
    page = await adapter.search(SearchQuery())
    listing = await adapter.get(page.items[0].source_id)
    assert listing is not None
    return listing


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


async def test_search_without_filters_returns_a_page(adapter: MarketplaceAdapter) -> None:
    page = await adapter.search(SearchQuery())
    assert page.total > 0
    assert page.items
    assert all(item.source == adapter.name for item in page.items)


async def test_search_sort_is_stable_across_calls(adapter: MarketplaceAdapter) -> None:
    q = SearchQuery(sort=SortKey.PRICE_ASC)
    first = await adapter.search(q)
    second = await adapter.search(q)
    assert [i.id for i in first.items] == [i.id for i in second.items]


@pytest.mark.parametrize("sort", list(SortKey))
async def test_every_sort_key_produces_a_total_order(
    adapter: MarketplaceAdapter, sort: SortKey
) -> None:
    """No sort may fall back to insertion order (CONSTITUTION II.2)."""
    page = await adapter.search(SearchQuery(sort=sort))
    again = await adapter.search(SearchQuery(sort=sort))
    assert [i.id for i in page.items] == [i.id for i in again.items]


async def test_pagination_has_no_overlap_and_no_gap(adapter: MarketplaceAdapter) -> None:
    """Page 1 + page 2 must equal the first 2N of a single ordered scan.

    Overlap means a duplicate in the model's context; a gap means a listing the user can
    never reach. Both come from an unstable sort, which is why the tie-break exists.
    """
    size = 7
    page1 = await adapter.search(SearchQuery(page=1, page_size=size, sort=SortKey.PRICE_ASC))
    page2 = await adapter.search(SearchQuery(page=2, page_size=size, sort=SortKey.PRICE_ASC))

    ids1 = [i.id for i in page1.items]
    ids2 = [i.id for i in page2.items]
    assert not set(ids1) & set(ids2), "pages overlap"

    wide = await adapter.search(SearchQuery(page=1, page_size=2 * size, sort=SortKey.PRICE_ASC))
    assert ids1 + ids2 == [i.id for i in wide.items], "page boundary loses or reorders rows"
    assert page1.total == page2.total == wide.total


async def test_page_size_is_capped(adapter: MarketplaceAdapter) -> None:
    """CONSTITUTION II.7 -- a caller cannot ask for more than the cap."""
    with pytest.raises(ValueError):
        SearchQuery(page_size=999)


async def test_search_returns_summaries_within_the_token_budget(
    adapter: MarketplaceAdapter,
) -> None:
    """Gate 1.9. Result-size discipline starts in P1, not P2."""
    page = await adapter.search(SearchQuery())
    for item in page.items:
        tokens = summary_token_estimate(item)
        assert tokens <= MAX_SUMMARY_TOKENS, f"{item.source_id} summary is {tokens} tokens"


async def test_unknown_filters_raise_rather_than_being_ignored() -> None:
    """A search that silently drops a filter is worse than one that fails: the caller
    believes the constraint was applied and the user sees results that violate it.
    """
    with pytest.raises(ValueError):
        SearchQuery(max_milage_km=50_000)  # type: ignore[call-arg]  # deliberate typo


# -- every filter in SearchQuery is honoured ---------------------------------------


async def test_filter_category(adapter: MarketplaceAdapter) -> None:
    everything = await adapter.search(SearchQuery(page_size=20))
    category = everything.items[0].category
    page = await adapter.search(SearchQuery(categories=(category,)))
    assert page.total > 0
    assert all(item.category is category for item in page.items)


async def test_filter_brand(adapter: MarketplaceAdapter) -> None:
    everything = await adapter.search(SearchQuery())
    brand = everything.items[0].brand
    page = await adapter.search(SearchQuery(brands=(brand,)))
    assert page.total > 0
    assert all(item.brand == brand for item in page.items)


async def test_filter_max_mileage(adapter: MarketplaceAdapter) -> None:
    page = await adapter.search(SearchQuery(max_mileage_km=40_000))
    assert all(item.mileage_km <= 40_000 for item in page.items)


async def test_filter_min_year(adapter: MarketplaceAdapter) -> None:
    page = await adapter.search(SearchQuery(min_year=2023))
    assert all(item.year >= 2023 for item in page.items)


async def test_filter_offer_type(adapter: MarketplaceAdapter) -> None:
    for wanted in (OfferType.BUY, OfferType.RENT):
        page = await adapter.search(SearchQuery(offer_type=wanted))
        for item in page.items:
            if wanted is OfferType.BUY:
                assert item.offer_type.is_buyable
            else:
                assert item.offer_type.is_rentable


async def test_filter_max_price_excludes_unpriced_listings(adapter: MarketplaceAdapter) -> None:
    from src.domain.money import Money

    ceiling = Money.of("18000")
    page = await adapter.search(SearchQuery(max_price=ceiling))
    for item in page.items:
        assert item.price_buy is not None, "a max_price filter must not return unpriced rows"
        assert item.price_buy <= ceiling


async def test_filter_available_between(adapter: MarketplaceAdapter) -> None:
    page = await adapter.search(SearchQuery(available_between=WINDOW))
    assert all(item.available_from <= WINDOW.end for item in page.items)


async def test_filter_radius(adapter: MarketplaceAdapter) -> None:
    from src.domain.marketplace import GeoPoint

    berlin = GeoPoint(latitude=52.5200, longitude=13.4050)
    page = await adapter.search(SearchQuery(near=berlin, within_km=150.0))
    assert page.total > 0
    for item in page.items:
        full = await adapter.get(item.source_id)
        assert full is not None
        here = GeoPoint(latitude=full.location.latitude, longitude=full.location.longitude)
        assert here.distance_km(berlin) <= 150.0


async def test_radius_requires_both_halves() -> None:
    from src.domain.marketplace import GeoPoint

    with pytest.raises(ValueError):
        SearchQuery(near=GeoPoint(latitude=52.0, longitude=13.0))


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


async def test_get_round_trips_an_id_from_search(adapter: MarketplaceAdapter) -> None:
    page = await adapter.search(SearchQuery())
    for item in page.items:
        listing = await adapter.get(item.source_id)
        assert listing is not None
        assert listing.id == item.id
        assert listing.source_id == item.source_id


async def test_get_on_unknown_id_returns_none_and_never_raises(
    adapter: MarketplaceAdapter,
) -> None:
    """ "Is this listing still there?" has a legitimate negative answer."""
    assert await adapter.get("does-not-exist") is None
    assert await adapter.get("") is None


async def test_every_listing_validates_and_retains_raw(adapter: MarketplaceAdapter) -> None:
    """CONSTITUTION II.6: normalise to `Listing`, retain `raw`."""
    page = await adapter.search(SearchQuery(page_size=20))
    for item in page.items:
        listing = await adapter.get(item.source_id)
        assert listing is not None
        assert listing.raw, f"{item.source_id} lost its upstream payload"
        # A full re-validation of the dumped record -- the normalisation is only correct if
        # it survives the round trip a database write will subject it to.
        assert Listing.model_validate(listing.model_dump(mode="json")) == listing


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------


async def test_availability_semantics_match_the_adapter_kind(
    adapter: MarketplaceAdapter,
) -> None:
    listing = await _first_listing(adapter)
    result = await adapter.availability(listing.source_id, WINDOW)

    assert result.source_id == listing.source_id
    assert result.requested == WINDOW

    if adapter.kind is MarketplaceKind.DEALER:
        # A forecourt car is not booked out by the day.
        assert result.status is AvailabilityStatus.ALWAYS
        assert result.free_windows == (WINDOW,)
    else:
        assert result.status is not AvailabilityStatus.ALWAYS
        for window in result.free_windows:
            assert window.start >= WINDOW.start
            assert window.end <= WINDOW.end


async def test_availability_reports_real_windows_on_a_rental_adapter(
    adapter: MarketplaceAdapter,
) -> None:
    """A rental marketplace whose every answer is "yes" is not modelling availability."""
    if adapter.kind is not MarketplaceKind.RENTAL:
        pytest.skip("rental adapters only")

    page = await adapter.search(SearchQuery(offer_type=OfferType.RENT, page_size=20))
    statuses = set()
    for item in page.items:
        statuses.add((await adapter.availability(item.source_id, WINDOW)).status)
    assert len(statuses) > 1, f"every listing reported {statuses}; bookings are not modelled"


async def test_availability_on_unknown_id_raises(adapter: MarketplaceAdapter) -> None:
    with pytest.raises(ListingNotFoundError):
        await adapter.availability("does-not-exist", WINDOW)


# ---------------------------------------------------------------------------
# quote
# ---------------------------------------------------------------------------


async def test_quote_is_itemised_and_totals_correctly(adapter: MarketplaceAdapter) -> None:
    listing = await _first_listing(adapter)
    terms = (
        QuoteTerms(window=WINDOW, expected_km_per_day=180)
        if listing.offer_type.is_rentable
        else QuoteTerms()
    )
    quote = await adapter.quote(listing.source_id, terms)

    assert quote.lines, "a quote with no lines cannot be explained to a user"
    assert quote.source == adapter.name
    assert quote.listing_id == listing.id
    assert quote.kind is not OfferType.BOTH

    running = quote.lines[0].amount
    for line in quote.lines[1:]:
        running = running + line.amount
    assert running == quote.total


async def test_rental_pricing_is_nonlinear(adapter: MarketplaceAdapter) -> None:
    """PHASE-5 §5: weekly is not daily x 7.

    If it were, the rent path would be inflated by roughly a third over a long horizon and
    the buy path would win every break-even by construction.
    """
    page = await adapter.search(SearchQuery(offer_type=OfferType.RENT, page_size=5))
    if not page.items:
        pytest.skip("adapter carries no rentable listings")

    source_id = page.items[0].source_id
    one_day = DateRange(start="2026-05-04", end="2026-05-04")
    one_week = DateRange(start="2026-05-04", end="2026-05-10")

    daily = await adapter.quote(source_id, QuoteTerms(window=one_day, include_insurance=False))
    weekly = await adapter.quote(source_id, QuoteTerms(window=one_week, include_insurance=False))

    assert one_week.days == 7
    assert weekly.total < daily.total * 7


async def test_quote_rejects_terms_it_cannot_price(adapter: MarketplaceAdapter) -> None:
    page = await adapter.search(SearchQuery(offer_type=OfferType.RENT, page_size=20))
    rent_only = [item for item in page.items if item.offer_type is OfferType.RENT]
    if not rent_only:
        pytest.skip("adapter carries no rent-only listings")

    with pytest.raises(QuoteNotAvailableError):
        await adapter.quote(rent_only[0].source_id, QuoteTerms())


async def test_quote_on_unknown_id_raises(adapter: MarketplaceAdapter) -> None:
    with pytest.raises(ListingNotFoundError):
        await adapter.quote("does-not-exist", QuoteTerms())


async def test_quote_terms_reject_unknown_fields() -> None:
    with pytest.raises(ValueError):
        QuoteTerms(insurance=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


async def test_adapter_satisfies_the_protocol(adapter: MarketplaceAdapter) -> None:
    assert isinstance(adapter, MarketplaceAdapter)
    info = adapter.info()
    assert info.name == adapter.name
    assert info.kind is adapter.kind


async def test_adapters_do_not_leak_each_others_listings(adapter: MarketplaceAdapter) -> None:
    """Nothing above `src/adapters` branches on source, so a leak here is invisible later."""
    page = await adapter.search(SearchQuery(page_size=20))
    assert {item.source for item in page.items} == {adapter.name}
