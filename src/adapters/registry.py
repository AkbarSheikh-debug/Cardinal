"""The set of adapters the rest of the system can see.

Two things depend on this being a registry rather than two hardcoded constructor calls:
the contract suite parametrises over `registered_adapters()`, so a new adapter is tested
the moment it is registered rather than when someone remembers to add it; and P2 fans its
`search_cars` tool out across whatever is registered, so nothing above `src/adapters`
enumerates marketplaces by name.
"""

from __future__ import annotations

from src.adapters.mock.autobazaar import MockAutoBazaar
from src.adapters.mock.drivenow import MockDriveNow
from src.adapters.protocol import MarketplaceAdapter
from src.adapters.store import ListingStore

#: Every adapter class the application knows about. Adding a real marketplace is one entry
#: here plus one new file -- which is the whole point of CONSTITUTION II.6.
ADAPTER_CLASSES: tuple[type[MockAutoBazaar] | type[MockDriveNow], ...] = (
    MockAutoBazaar,
    MockDriveNow,
)


def registered_adapters(store: ListingStore) -> tuple[MarketplaceAdapter, ...]:
    return tuple(cls(store) for cls in ADAPTER_CLASSES)


def adapter_by_name(store: ListingStore, name: str) -> MarketplaceAdapter:
    for adapter in registered_adapters(store):
        if adapter.name == name:
            return adapter
    known = ", ".join(cls.name for cls in ADAPTER_CLASSES)
    raise KeyError(f"no adapter named {name!r}; registered: {known}")


def registered_source_names() -> tuple[str, ...]:
    return tuple(cls.name for cls in ADAPTER_CLASSES)
