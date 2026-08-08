"""Shared implementation for the two mock marketplaces.

Both mocks are thin: they hold a name, a kind, and a store. Everything that differs between
a rental marketplace and a dealer lives in `availability` and in which offer types their
slice of the catalogue carries -- which is the point. If the mocks needed to differ
anywhere else, the protocol would be wrong.

Nothing here reads the clock. A quote's validity is anchored to `CATALOGUE_EPOCH` so two
runs of the seed and two runs of the contract suite produce identical output (gate 1.6).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from src.adapters.catalogue.generator import CATALOGUE_EPOCH
from src.adapters.protocol import ListingNotFoundError, QuoteNotAvailableError
from src.adapters.store import ListingStore
from src.domain.dates import DateRange
from src.domain.enums import Currency, MarketplaceKind, OfferType
from src.domain.listing import Listing, ListingSummary
from src.domain.marketplace import (
    AdapterInfo,
    Availability,
    AvailabilityStatus,
    Quote,
    QuoteLine,
    QuoteTerms,
    SearchPage,
    SearchQuery,
)
from src.domain.money import Money

#: How long a quote stands. Fixed offset from the catalogue epoch, not from "now".
QUOTE_VALIDITY_DAYS = 14

#: Buy-path transaction costs. Real ones, because omitting them biases every rent-vs-buy
#: comparison toward buying (PHASE-5 §5).
REGISTRATION_RATE = Decimal("0.015")
DEALER_ADMIN_FEE = Decimal("180.00")

#: Daily insurance surcharge, as a fraction of the daily rate, when the listing does not
#: already include cover and the caller asked for it.
INSURANCE_RATE = Decimal("0.12")


class MockMarketplaceAdapter:
    """Base for `MockDriveNow` and `MockAutoBazaar`."""

    name: str
    kind: MarketplaceKind
    display_name: str

    def __init__(self, store: ListingStore) -> None:
        self._store = store

    def info(self) -> AdapterInfo:
        return AdapterInfo(name=self.name, kind=self.kind, display_name=self.display_name)

    # -- search / get ---------------------------------------------------------------

    async def search(self, q: SearchQuery) -> SearchPage:
        listings, total = await self._store.query(q, sources=[self.name])
        return SearchPage(
            items=tuple(ListingSummary.from_listing(item) for item in listings),
            total=total,
            page=q.page,
            page_size=q.page_size,
        )

    async def get(self, source_id: str) -> Listing | None:
        """`None` for an unknown id, never an exception -- see `ListingNotFoundError`."""
        return await self._store.fetch(self.name, source_id)

    async def _require(self, source_id: str) -> Listing:
        listing = await self.get(source_id)
        if listing is None:
            raise ListingNotFoundError(f"{self.name} has no listing {source_id!r}")
        return listing

    # -- availability ---------------------------------------------------------------

    async def availability(self, source_id: str, window: DateRange) -> Availability:
        raise NotImplementedError

    # -- quote ----------------------------------------------------------------------

    async def quote(self, source_id: str, terms: QuoteTerms) -> Quote:
        listing = await self._require(source_id)
        wants_rental = terms.window is not None

        if wants_rental:
            if not listing.offer_type.is_rentable:
                raise QuoteNotAvailableError(f"{source_id} is not offered for rent")
            lines, kind = self._rental_lines(listing, terms), OfferType.RENT
        else:
            if not listing.offer_type.is_buyable:
                raise QuoteNotAvailableError(
                    f"{source_id} is rent-only; a quote needs a rental window"
                )
            lines, kind = self._purchase_lines(listing, terms), OfferType.BUY

        total = lines[0].amount
        for line in lines[1:]:
            total = total + line.amount

        return Quote(
            source=self.name,
            source_id=source_id,
            listing_id=listing.id,
            kind=kind,
            lines=lines,
            total=total,
            valid_until=(CATALOGUE_EPOCH + timedelta(days=QUOTE_VALIDITY_DAYS)).date(),
            terms=terms,
        )

    def _purchase_lines(self, listing: Listing, terms: QuoteTerms) -> tuple[QuoteLine, ...]:
        assert listing.price_buy is not None  # guarded by offer_type.is_buyable
        price = listing.price_buy
        lines = [
            QuoteLine(label="Vehicle price", amount=price),
            QuoteLine(
                label="Registration and transfer",
                amount=_money(price.amount * REGISTRATION_RATE, price.currency),
            ),
            QuoteLine(
                label="Dealer administration", amount=_money(DEALER_ADMIN_FEE, price.currency)
            ),
        ]
        if terms.trade_in_value is not None:
            lines.append(QuoteLine(label="Trade-in allowance", amount=-terms.trade_in_value))
        return tuple(lines)

    def _rental_lines(self, listing: Listing, terms: QuoteTerms) -> tuple[QuoteLine, ...]:
        assert listing.rental_rates is not None  # guarded by offer_type.is_rentable
        assert terms.window is not None
        rates = listing.rental_rates
        days = terms.window.days

        # Tiered, not linear. `daily x days` would inflate a month-long rental by roughly a
        # third and hand every long-horizon break-even to the buy path by construction.
        months, rest = divmod(days, 30)
        weeks, spare_days = divmod(rest, 7)
        base = rates.monthly * months + rates.weekly * weeks + rates.daily * spare_days
        detail = _tier_detail(months, weeks, spare_days)
        lines = [QuoteLine(label=f"Rental, {days} days ({detail})", amount=base)]

        if terms.include_insurance and not rates.insurance_included:
            lines.append(
                QuoteLine(
                    label="Insurance",
                    amount=_money(rates.daily.amount * INSURANCE_RATE * days, rates.daily.currency),
                )
            )

        if terms.expected_km_per_day is not None:
            excess_per_day = terms.expected_km_per_day - rates.included_km_per_day
            if excess_per_day > 0:
                lines.append(
                    QuoteLine(
                        label=f"Excess mileage, {excess_per_day} km/day",
                        amount=_money(
                            rates.excess_km_rate.amount * excess_per_day * days,
                            rates.excess_km_rate.currency,
                        ),
                    )
                )
        return tuple(lines)


def _money(amount: Decimal, currency: Currency) -> Money:
    return Money(amount=amount, currency=currency)


def _tier_detail(months: int, weeks: int, days: int) -> str:
    parts = []
    if months:
        parts.append(f"{months}x monthly")
    if weeks:
        parts.append(f"{weeks}x weekly")
    if days:
        parts.append(f"{days}x daily")
    return " + ".join(parts) if parts else "no chargeable days"


def blocked_windows_from_raw(listing: Listing) -> tuple[DateRange, ...]:
    """Read existing bookings back out of the untouched upstream payload.

    They live in `raw` rather than on `Listing` because a dealer feed has no such concept,
    and `Listing` is the shape *every* adapter normalises to.
    """
    windows = listing.raw.get("blockedWindows") or []
    return tuple(
        DateRange.model_validate({"start": window["from"], "end": window["to"]})
        for window in windows
    )


def availability_always(source_id: str, window: DateRange) -> Availability:
    return Availability(
        source_id=source_id,
        requested=window,
        status=AvailabilityStatus.ALWAYS,
        free_windows=(window,),
    )
