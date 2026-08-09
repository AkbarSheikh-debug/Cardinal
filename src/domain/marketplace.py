"""Marketplace query and result contracts (PHASE-1 §3, §5).

`SearchQuery` forbids unknown fields. The contract suite asserts that an unrecognised
filter *raises* rather than being silently ignored -- a search that quietly drops
`max_mileage_km` and returns 240 rows is worse than one that fails, because the caller
believes the filter was applied.
"""

from __future__ import annotations

import math
import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.dates import DateRange
from src.domain.enums import (
    FuelType,
    MarketplaceKind,
    OfferType,
    Transmission,
    VehicleCategory,
    VehicleCondition,
)
from src.domain.listing import ListingSummary
from src.domain.money import Money

#: CONSTITUTION II.7 / PHASE-2 §6. A hard cap, not a default -- a caller cannot ask for more.
MAX_PAGE_SIZE = 20

#: PHASE-1 §7 criterion 1.9. Per summary, not per page.
MAX_SUMMARY_TOKENS = 200


class SortKey(StrEnum):
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    YEAR_DESC = "year_desc"
    MILEAGE_ASC = "mileage_asc"
    AVAILABLE_SOONEST = "available_soonest"


class GeoPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)

    def distance_km(self, other: GeoPoint) -> float:
        """Great-circle distance. Pure maths -- no geo library, no I/O in `src/domain`."""
        radius_km = 6371.0088
        lat1, lon1, lat2, lon2 = map(
            math.radians, (self.latitude, self.longitude, other.latitude, other.longitude)
        )
        dlat, dlon = lat2 - lat1, lon2 - lon1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * radius_km * math.asin(math.sqrt(h))


class SearchQuery(BaseModel):
    """Structured search. Every field here is honoured by every adapter, or the contract
    suite fails.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    categories: tuple[VehicleCategory, ...] = ()
    brands: tuple[str, ...] = ()
    fuel_types: tuple[FuelType, ...] = ()
    transmissions: tuple[Transmission, ...] = ()
    #: PLAN-02 P13 / proposal doc #2. A first-class filter beside `offer_type`, not folded
    #: into it: "buy or rent" and "new or used" are orthogonal questions.
    conditions: tuple[VehicleCondition, ...] = ()
    offer_type: OfferType | None = None
    max_price: Money | None = Field(default=None, description="Against price_buy.")
    max_rental_daily: Money | None = None
    max_mileage_km: int | None = Field(default=None, ge=0)
    min_year: int | None = Field(default=None, ge=1990)
    min_seats: int | None = Field(default=None, ge=2, le=9)
    available_between: DateRange | None = None
    near: GeoPoint | None = None
    within_km: float | None = Field(default=None, gt=0)
    include_withdrawn: bool = False

    sort: SortKey = SortKey.PRICE_ASC
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=MAX_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @model_validator(mode="after")
    def _geo_filter_is_complete(self) -> Self:
        if (self.near is None) != (self.within_km is None):
            raise ValueError("`near` and `within_km` must be supplied together")
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class SearchPage(BaseModel):
    """Summaries plus a total count. Never full records (PHASE-1 §5)."""

    model_config = ConfigDict(frozen=True)

    items: tuple[ListingSummary, ...]
    total: int = Field(ge=0, description="Matches across all pages, not just this one.")
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)

    @model_validator(mode="after")
    def _page_is_not_oversized(self) -> Self:
        if len(self.items) > self.page_size:
            raise ValueError("page carries more items than its own page_size")
        return self

    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total


class AvailabilityStatus(StrEnum):
    ALWAYS = "always"
    """A dealer forecourt car is not booked out by the day. Dealer adapters return this."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class Availability(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    requested: DateRange
    status: AvailabilityStatus
    free_windows: tuple[DateRange, ...] = Field(
        default=(), description="Sub-ranges of `requested` that are actually bookable."
    )

    @model_validator(mode="after")
    def _windows_match_status(self) -> Self:
        if self.status is AvailabilityStatus.UNAVAILABLE and self.free_windows:
            raise ValueError("UNAVAILABLE must carry no free windows")
        if self.status in (AvailabilityStatus.AVAILABLE, AvailabilityStatus.ALWAYS):
            if self.free_windows != (self.requested,):
                raise ValueError(f"{self.status} must report the whole requested window as free")
        if self.status is AvailabilityStatus.PARTIAL and not self.free_windows:
            raise ValueError("PARTIAL must carry at least one free window")
        for window in self.free_windows:
            if window.start < self.requested.start or window.end > self.requested.end:
                raise ValueError("a free window escapes the requested range")
        return self


class QuoteTerms(BaseModel):
    """What the price depends on.

    `quote` is deliberately separate from `get` (PHASE-1 §3): rental pricing depends on
    dates and duration, and folding that into the listing record is the mistake that makes
    rental adapters impossible to add later.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    window: DateRange | None = Field(default=None, description="Required for a rental quote.")
    expected_km_per_day: int | None = Field(default=None, ge=0)
    include_insurance: bool = True
    trade_in_value: Money | None = Field(default=None, description="Buy path only.")


class QuoteLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    amount: Money


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    source_id: str
    listing_id: uuid.UUID
    kind: OfferType = Field(description="Whether this quote prices a purchase or a rental.")
    lines: tuple[QuoteLine, ...]
    total: Money
    valid_until: date
    terms: QuoteTerms

    @model_validator(mode="after")
    def _total_is_the_sum(self) -> Self:
        if not self.lines:
            raise ValueError("a quote with no lines cannot be explained to a user")
        running = self.lines[0].amount
        for line in self.lines[1:]:
            running = running + line.amount
        if running != self.total:
            raise ValueError(f"quote total {self.total} != sum of lines {running}")
        if self.kind is OfferType.BOTH:
            raise ValueError("a quote prices exactly one path; 'both' is not a quote kind")
        return self


class AdapterInfo(BaseModel):
    """What the registry knows about an adapter without instantiating a search."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: MarketplaceKind
    display_name: str


class UnknownFilterError(ValueError):
    """Raised when a caller passes a filter the query model does not define."""


def estimate_tokens(text: str) -> int:
    """Deliberately a heuristic, and deliberately a pessimistic one.

    Gate 1.9 needs a token count with no network call and no API key, so this uses the
    standard ~4-characters-per-token approximation and rounds up. It over-counts JSON
    slightly (punctuation-dense text tokenises worse than prose), which is the safe
    direction for a budget check.
    """
    return math.ceil(len(text) / 4)


def summary_token_estimate(summary: ListingSummary) -> int:
    return estimate_tokens(summary.model_dump_json())


def money_sort_key(value: Money | None) -> Decimal:
    """`None` sorts last on an ascending price sort rather than crashing the comparison."""
    return value.amount if value is not None else Decimal("Infinity")


def date_sort_key(value: date) -> date:
    return value
