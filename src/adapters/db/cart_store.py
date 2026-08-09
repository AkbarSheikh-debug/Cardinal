"""`PostgresCartStore` -- the durable path for `src/adapters/cart_store.py`'s `CartStore`.

No `canonical` column here, unlike `listings`/`bookings`/`dealers`: a `CartItem` is five
scalars and a timestamp with no nested structure to lose, so projected columns *are* the
record. Adding a JSONB document would be duplication with nothing to justify it.

Every query filters on `account_id` inside the SQL rather than fetching and filtering in
Python (CONSTITUTION IV.4) -- gate 14.11's cross-account isolation is a property of the
queries, not of a check a caller might forget.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.models import CartItemRow
from src.domain.cart import Cart, CartItem
from src.domain.enums import OfferType


class PostgresCartStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, account_id: uuid.UUID) -> Cart:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(CartItemRow)
                .where(CartItemRow.account_id == account_id)
                # Oldest first, so the cart reads in the order the buyer built it.
                .order_by(CartItemRow.added_at, CartItemRow.id)
            )
            return Cart(account_id=account_id, items=tuple(_to_item(row) for row in rows))

    async def add(self, account_id: uuid.UUID, item: CartItem) -> Cart:
        async with self._sessions() as session:
            session.add(
                CartItemRow(
                    id=item.id,
                    account_id=account_id,
                    listing_id=item.listing_id,
                    source=item.source,
                    source_id=item.source_id,
                    offer_type=item.offer_type.value,
                    added_at=item.added_at,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                # The UNIQUE natural key caught a double-add. That is the *expected* outcome
                # of a double-clicked button, not an error worth surfacing -- roll back and
                # return the cart as it already stands, matching `Cart.with_item`'s
                # idempotency exactly.
                await session.rollback()
        return await self.get(account_id)

    async def remove(self, account_id: uuid.UUID, item_id: uuid.UUID) -> Cart:
        async with self._sessions() as session:
            # `account_id` in the WHERE clause, not checked afterwards: this is what makes
            # "delete someone else's cart item" unexpressible rather than merely refused.
            await session.execute(
                delete(CartItemRow).where(
                    CartItemRow.id == item_id, CartItemRow.account_id == account_id
                )
            )
            await session.commit()
        return await self.get(account_id)

    async def clear(self, account_id: uuid.UUID) -> Cart:
        async with self._sessions() as session:
            await session.execute(delete(CartItemRow).where(CartItemRow.account_id == account_id))
            await session.commit()
        return await self.get(account_id)


def _to_item(row: CartItemRow) -> CartItem:
    return CartItem(
        id=row.id,
        listing_id=row.listing_id,
        source=row.source,
        source_id=row.source_id,
        offer_type=OfferType(row.offer_type),
        added_at=row.added_at,
    )
