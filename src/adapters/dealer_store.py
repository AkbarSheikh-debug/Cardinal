"""Where the dealer directory lives, behind an interface -- the same protocol/in-memory/
Postgres split `src/adapters/store.py` makes for listings (PLAN-02 P13).

Deliberately read-only. The directory is *generated* (`src/adapters/catalogue/dealers.py`)
and seeded (`scripts/seed_marketplace.py`); nothing in the running application creates or
edits a dealer, so a write method here would be an affordance with no caller and a surface
for P15 to accidentally mutate the thing it is meant to route leads to.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from src.adapters.catalogue.dealers import generate_dealers
from src.adapters.catalogue.generator import DEFAULT_SEED, SOURCES
from src.domain.dealer import Dealer, PayeeIdentity


class DealerDirectory(Protocol):
    async def get(self, dealer_id: uuid.UUID) -> Dealer | None: ...

    async def by_ref(self, source: str, dealer_ref: str) -> Dealer | None: ...

    async def all(self) -> tuple[Dealer, ...]: ...

    async def payee(self, dealer_id: uuid.UUID | None) -> PayeeIdentity | None:
        """The disclosure P14's checkout renders, or `None` when the listing has no dealer.

        `None` in, `None` out rather than a raise: `Listing.dealer_id` is nullable until a
        re-seed fills it, and a checkout that 500s because a row predates P13 would be a
        worse failure than one that renders without the block and says so.
        """
        ...


class InMemoryDealerDirectory:
    """The generated directory in a dict. Used by tests, gates and `DEMO_MODE`."""

    def __init__(self, dealers: tuple[Dealer, ...]) -> None:
        self._by_id: dict[uuid.UUID, Dealer] = {d.id: d for d in dealers}
        self._by_ref: dict[tuple[str, str], Dealer] = {d.natural_key: d for d in dealers}
        self._ordered = dealers

    @classmethod
    def seeded(cls, seed: int = DEFAULT_SEED) -> InMemoryDealerDirectory:
        """The same directory `generate_catalogue` assigned listings to -- same seed, same
        sources. Anything else would produce a store whose ids don't match the catalogue's,
        which fails as a confusing `None` rather than as an obvious error."""
        return cls(generate_dealers(seed, SOURCES))

    async def get(self, dealer_id: uuid.UUID) -> Dealer | None:
        return self._by_id.get(dealer_id)

    async def by_ref(self, source: str, dealer_ref: str) -> Dealer | None:
        return self._by_ref.get((source, dealer_ref))

    async def all(self) -> tuple[Dealer, ...]:
        return self._ordered

    async def payee(self, dealer_id: uuid.UUID | None) -> PayeeIdentity | None:
        return await resolve_payee(self, dealer_id)


async def resolve_payee(
    directory: DealerDirectory, dealer_id: uuid.UUID | None
) -> PayeeIdentity | None:
    """Shared by every `DealerDirectory` implementation -- `Protocol` has no default bodies,
    so both call through this rather than each re-deriving the same two lines."""
    if dealer_id is None:
        return None
    dealer = await directory.get(dealer_id)
    return PayeeIdentity.of(dealer) if dealer is not None else None
