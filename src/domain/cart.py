"""The buyer's cart (PLAN-02 P14).

A cart of *cars* is not a cart of groceries, and two rules follow from that:

- **Adding the same listing twice is idempotent, not a quantity of two.** Every listing is
  one physical vehicle. A cart that lets you hold two of `AB-1073` is describing something
  that does not exist, and the bug it produces downstream -- a checkout priced for two cars
  that only one of exists -- is much worse than the double-click it came from.
- **Checkout runs on one item.** The cart may hold several (comparing three cars in a cart is
  a perfectly ordinary thing to do), but P8's booking lifecycle, quote path and gesture token
  are all single-listing, and widening them is a real change rather than a loop. `[MVP]` is
  one car per checkout; the cart is a shortlist you pick from.

Pure: no clock, no database, no network (CONSTITUTION II.1). `added_at` is passed in.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import OfferType


class CartItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    listing_id: uuid.UUID
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    #: What the buyer intends to do with it. The same car can legitimately be in one cart to
    #: rent and another to buy, so this is part of the identity below, not a detail.
    offer_type: OfferType
    added_at: datetime

    @property
    def natural_key(self) -> tuple[str, str, OfferType]:
        return (self.source, self.source_id, self.offer_type)


class Cart(BaseModel):
    """One account's shortlist. Immutable -- every mutation returns a new `Cart`."""

    model_config = ConfigDict(frozen=True)

    account_id: uuid.UUID
    items: tuple[CartItem, ...] = ()

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def is_empty(self) -> bool:
        return not self.items

    def find(self, item_id: uuid.UUID) -> CartItem | None:
        return next((item for item in self.items if item.id == item_id), None)

    def contains(self, source: str, source_id: str, offer_type: OfferType) -> bool:
        return any(item.natural_key == (source, source_id, offer_type) for item in self.items)

    def with_item(self, item: CartItem) -> Self:
        """Idempotent on `(source, source_id, offer_type)` -- see this module's docstring.

        Returns `self` unchanged when the car is already there, so a double-clicked
        "Add to cart" is a no-op rather than a second line the buyer has to remove.
        """
        if self.contains(*item.natural_key):
            return self
        return type(self)(account_id=self.account_id, items=(*self.items, item))

    def without_item(self, item_id: uuid.UUID) -> Self:
        return type(self)(
            account_id=self.account_id,
            items=tuple(item for item in self.items if item.id != item_id),
        )

    def cleared(self) -> Self:
        return type(self)(account_id=self.account_id, items=())
