"""MockDriveNow -- a rental marketplace that also sells its ex-fleet cars.

That second half is not decoration: it is what gives the catalogue its `both` listings, and
a listing you can either rent or buy is precisely the case that makes P5's rent-vs-buy
break-even a real comparison rather than a comparison of two different cars.
"""

from __future__ import annotations

from src.adapters.mock.base import MockMarketplaceAdapter, blocked_windows_from_raw
from src.domain.dates import DateRange
from src.domain.enums import MarketplaceKind
from src.domain.marketplace import Availability, AvailabilityStatus


class MockDriveNow(MockMarketplaceAdapter):
    name = "mock_drivenow"
    kind = MarketplaceKind.RENTAL
    display_name = "DriveNow"

    async def availability(self, source_id: str, window: DateRange) -> Availability:
        """Real windows, computed against the listing's existing bookings."""
        listing = await self._require(source_id)

        # A car that has not arrived yet is not bookable at the front of the window.
        if listing.available_from > window.end:
            return Availability(
                source_id=source_id,
                requested=window,
                status=AvailabilityStatus.UNAVAILABLE,
            )
        usable = DateRange(start=max(window.start, listing.available_from), end=window.end)

        free: list[DateRange] = [usable]
        for blocked in blocked_windows_from_raw(listing):
            if not blocked.overlaps(usable):
                continue
            free = [part for candidate in free for part in candidate.subtract(blocked)]

        if not free:
            return Availability(
                source_id=source_id, requested=window, status=AvailabilityStatus.UNAVAILABLE
            )

        windows = tuple(sorted(free, key=lambda w: w.start))
        status = (
            AvailabilityStatus.AVAILABLE if windows == (window,) else AvailabilityStatus.PARTIAL
        )
        return Availability(
            source_id=source_id, requested=window, status=status, free_windows=windows
        )
