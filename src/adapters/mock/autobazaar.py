"""MockAutoBazaar -- a dealer marketplace. Buy only."""

from __future__ import annotations

from src.adapters.mock.base import MockMarketplaceAdapter, availability_always
from src.domain.dates import DateRange
from src.domain.enums import MarketplaceKind
from src.domain.marketplace import Availability


class MockAutoBazaar(MockMarketplaceAdapter):
    name = "mock_autobazaar"
    kind = MarketplaceKind.DEALER
    display_name = "AutoBazaar"

    async def availability(self, source_id: str, window: DateRange) -> Availability:
        """`ALWAYS`. A forecourt car is not booked out by the day.

        When a car can first be collected is `available_from`, which search already
        surfaces -- folding it in here would make `availability` mean two different things
        depending on the adapter, which is the branch the protocol exists to prevent.
        """
        await self._require(source_id)  # unknown ids are a caller bug, not an empty result
        return availability_always(source_id, window)
