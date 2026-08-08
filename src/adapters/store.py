"""Where listings live, behind an interface.

The mock adapters do not own their data -- they read it from a `ListingStore`. That is what
lets the same two adapters run against an in-memory catalogue in the contract suite (no
container, no fixtures, milliseconds) and against Postgres in the deployed app, without a
line of adapter code changing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.adapters.catalogue.generator import generate_catalogue
from src.adapters.filtering import matches, paginate, sort_listings
from src.domain.listing import Listing
from src.domain.marketplace import SearchQuery


class ListingStore(Protocol):
    """Retrieval, scoped to a set of sources."""

    async def query(
        self, q: SearchQuery, *, sources: Sequence[str]
    ) -> tuple[tuple[Listing, ...], int]:
        """Matching listings for this page, plus the total across all pages."""
        ...

    async def fetch(self, source: str, source_id: str) -> Listing | None: ...

    async def count(self, *, sources: Sequence[str] | None = None) -> int: ...


class InMemoryListingStore:
    """The whole catalogue in a dict. Used by the contract suite and by `DEMO_MODE`."""

    def __init__(self, listings: Sequence[Listing]) -> None:
        self._by_key: dict[tuple[str, str], Listing] = {}
        for listing in listings:
            key = listing.natural_key
            if key in self._by_key:
                # UNIQUE (source, source_id) is the dedup primitive (PHASE-1 §6). Enforce it
                # here too, so the in-memory store can't accept data Postgres would reject.
                raise ValueError(f"duplicate listing for {key}")
            self._by_key[key] = listing

    @classmethod
    def seeded(cls, seed: int | None = None, total: int | None = None) -> InMemoryListingStore:
        kwargs = {}
        if seed is not None:
            kwargs["seed"] = seed
        if total is not None:
            kwargs["total"] = total
        return cls(generate_catalogue(**kwargs))

    @property
    def listings(self) -> tuple[Listing, ...]:
        return tuple(self._by_key.values())

    async def query(
        self, q: SearchQuery, *, sources: Sequence[str]
    ) -> tuple[tuple[Listing, ...], int]:
        wanted = set(sources)
        candidates = [
            listing
            for listing in self._by_key.values()
            if listing.source in wanted and matches(listing, q)
        ]
        page, total = paginate(sort_listings(candidates, q.sort), q)
        return tuple(page), total

    async def fetch(self, source: str, source_id: str) -> Listing | None:
        return self._by_key.get((source, source_id))

    async def count(self, *, sources: Sequence[str] | None = None) -> int:
        if sources is None:
            return len(self._by_key)
        wanted = set(sources)
        return sum(1 for listing in self._by_key.values() if listing.source in wanted)
