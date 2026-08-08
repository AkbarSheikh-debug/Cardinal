"""Marketplace adapters, storage and embeddings. Imports `src.domain` only.

CONSTITUTION II.6: every source implements `MarketplaceAdapter` and normalises to
`Listing` while retaining `raw`. Nothing above this package branches on which marketplace a
result came from.
"""

from src.adapters.protocol import (
    AdapterError,
    ListingNotFoundError,
    MarketplaceAdapter,
    QuoteNotAvailableError,
)
from src.adapters.registry import (
    ADAPTER_CLASSES,
    adapter_by_name,
    registered_adapters,
    registered_source_names,
)
from src.adapters.store import InMemoryListingStore, ListingStore

__all__ = [
    "ADAPTER_CLASSES",
    "AdapterError",
    "InMemoryListingStore",
    "ListingNotFoundError",
    "ListingStore",
    "MarketplaceAdapter",
    "QuoteNotAvailableError",
    "adapter_by_name",
    "registered_adapters",
    "registered_source_names",
]
