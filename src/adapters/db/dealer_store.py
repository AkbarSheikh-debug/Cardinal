"""`PostgresDealerDirectory` -- the durable path for `src/adapters/dealer_store.py`'s
`DealerDirectory` protocol, the same split `PostgresListingStore` makes for listings.

`canonical` is the only column a `Dealer` is rebuilt from (D-006's dual-storage shape).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.mapping import to_dealer
from src.adapters.db.models import DealerRow
from src.adapters.dealer_store import resolve_payee
from src.domain.dealer import Dealer, PayeeIdentity


class PostgresDealerDirectory:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, dealer_id: uuid.UUID) -> Dealer | None:
        async with self._sessions() as session:
            row = await session.get(DealerRow, dealer_id)
        return to_dealer(row) if row is not None else None

    async def by_ref(self, source: str, dealer_ref: str) -> Dealer | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(DealerRow).where(
                    DealerRow.source == source, DealerRow.dealer_ref == dealer_ref
                )
            )
        return to_dealer(row) if row is not None else None

    async def all(self) -> tuple[Dealer, ...]:
        async with self._sessions() as session:
            rows = await session.scalars(
                # Ordered, so two reads of the directory agree -- the same determinism
                # discipline the generator itself is held to (gate 13.2).
                select(DealerRow).order_by(DealerRow.source, DealerRow.dealer_ref)
            )
            return tuple(to_dealer(row) for row in rows)

    async def payee(self, dealer_id: uuid.UUID | None) -> PayeeIdentity | None:
        return await resolve_payee(self, dealer_id)
