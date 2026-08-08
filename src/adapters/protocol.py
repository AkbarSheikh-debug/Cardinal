"""The marketplace adapter protocol (PHASE-1 §3, CONSTITUTION II.6).

Four methods, chosen because they are the intersection of what every real marketplace
exposes. The important one is that `quote` is separate from `get`: rental pricing depends
on dates and duration, and folding that into the listing record is the specific mistake
that makes rental adapters impossible to add later.

Every adapter normalises to `Listing` and retains `raw`. Nothing above `src/adapters`
branches on which marketplace a result came from -- the agent only ever sees
`listing.source`. That is what makes "connect a real marketplace" a new file rather than a
rewrite.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.dates import DateRange
from src.domain.enums import MarketplaceKind
from src.domain.listing import Listing
from src.domain.marketplace import (
    AdapterInfo,
    Availability,
    Quote,
    QuoteTerms,
    SearchPage,
    SearchQuery,
)


class AdapterError(RuntimeError):
    """Base for every adapter-level failure."""


class ListingNotFoundError(AdapterError):
    """Raised by `quote`/`availability` for an id that does not exist.

    Note that `get` does *not* raise for an unknown id -- it returns `None`. The asymmetry
    is deliberate and the contract suite pins it: "is this listing still there?" is a
    question with a legitimate negative answer, whereas "price this listing" for something
    that does not exist is a caller bug.
    """


class QuoteNotAvailableError(AdapterError):
    """Raised when the terms cannot be priced -- e.g. a rental quote with no window."""


@runtime_checkable
class MarketplaceAdapter(Protocol):
    """What every marketplace, mock or real, implements."""

    name: str
    kind: MarketplaceKind

    def info(self) -> AdapterInfo: ...

    async def search(self, q: SearchQuery) -> SearchPage:
        """Structured search. Returns summaries and a total, never full records."""
        ...

    async def get(self, source_id: str) -> Listing | None:
        """Full record by the marketplace's own id. `None` when unknown -- never raises."""
        ...

    async def availability(self, source_id: str, window: DateRange) -> Availability:
        """Bookability across `window`.

        A rental adapter returns real free windows; a dealer adapter returns `ALWAYS`,
        because a forecourt car is not booked out by the day.
        """
        ...

    async def quote(self, source_id: str, terms: QuoteTerms) -> Quote:
        """Price this listing under these terms. Itemised, so the UI can explain it."""
        ...
