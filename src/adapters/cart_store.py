"""Where carts live, behind an interface -- the same protocol/in-memory/Postgres split every
other store in this package makes (PLAN-02 P14).

The whole surface is keyed on `account_id`, and there is deliberately no method that takes a
cart *id*: a cart is not an object a caller can name, it is whatever the signed-in account
currently holds. That is what makes "account A reads account B's cart" (gate 14.11) an
impossible request to phrase rather than a check somebody has to remember to write.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from src.domain.cart import Cart, CartItem
from src.domain.enums import OfferType
from src.domain.listing import Listing


class CartStore(Protocol):
    async def get(self, account_id: uuid.UUID) -> Cart: ...

    async def add(self, account_id: uuid.UUID, item: CartItem) -> Cart:
        """Idempotent on the item's natural key (see `Cart.with_item`)."""
        ...

    async def remove(self, account_id: uuid.UUID, item_id: uuid.UUID) -> Cart: ...

    async def clear(self, account_id: uuid.UUID) -> Cart: ...


def new_cart_item(
    listing: Listing, offer_type: OfferType, *, now: datetime | None = None
) -> CartItem:
    """Builds an item from a real `Listing`, so `listing_id`/`source`/`source_id` can never
    disagree with each other -- a client-supplied triple could, and a cart row pointing at a
    listing it doesn't match is the kind of thing that only shows up at checkout."""
    return CartItem(
        id=uuid.uuid4(),
        listing_id=listing.id,
        source=listing.source,
        source_id=listing.source_id,
        offer_type=offer_type,
        added_at=now or datetime.now(UTC),
    )


class InMemoryCartStore:
    """Every cart in a dict. Used by tests, gates and `DEMO_MODE`."""

    def __init__(self) -> None:
        self._carts: dict[uuid.UUID, Cart] = {}

    async def get(self, account_id: uuid.UUID) -> Cart:
        return self._carts.get(account_id) or Cart(account_id=account_id)

    async def add(self, account_id: uuid.UUID, item: CartItem) -> Cart:
        cart = (await self.get(account_id)).with_item(item)
        self._carts[account_id] = cart
        return cart

    async def remove(self, account_id: uuid.UUID, item_id: uuid.UUID) -> Cart:
        cart = (await self.get(account_id)).without_item(item_id)
        self._carts[account_id] = cart
        return cart

    async def clear(self, account_id: uuid.UUID) -> Cart:
        cart = (await self.get(account_id)).cleared()
        self._carts[account_id] = cart
        return cart
