"""`src/adapters/cart_store.py` -- PLAN-02 P14.

The protocol's whole surface is keyed on `account_id` and there is deliberately no method
taking a cart *id*. These assert that shape holds in practice: one account's mutations are
invisible to another's, and `new_cart_item` builds a line from a real `Listing` so its
`listing_id`/`source`/`source_id` can never disagree with each other.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.adapters.cart_store import InMemoryCartStore, new_cart_item
from src.domain.enums import OfferType
from tests.unit.helpers import make_listing

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
A = uuid.UUID("11111111-1111-1111-1111-111111111111")
B = uuid.UUID("22222222-2222-2222-2222-222222222222")


# -- new_cart_item ------------------------------------------------------------------


def test_an_item_built_from_a_listing_cannot_disagree_with_it() -> None:
    listing = make_listing(source="mock_drivenow", source_id="DN-7")
    entry = new_cart_item(listing, OfferType.RENT, now=NOW)

    assert entry.listing_id == listing.id
    assert entry.source == "mock_drivenow"
    assert entry.source_id == "DN-7"
    assert entry.offer_type is OfferType.RENT
    assert entry.added_at == NOW


def test_two_items_for_the_same_listing_get_different_ids() -> None:
    """The natural key deduplicates, not the row id -- so an id collision would be a bug
    that only shows up as one of two legitimate lines vanishing."""
    listing = make_listing()
    assert new_cart_item(listing, OfferType.BUY).id != new_cart_item(listing, OfferType.RENT).id


# -- the store ----------------------------------------------------------------------


async def test_an_unknown_account_gets_an_empty_cart_not_a_miss() -> None:
    """There is no "create a cart" call, and there shouldn't be: a cart is whatever the
    signed-in account currently holds, which for a new buyer is nothing."""
    cart = await InMemoryCartStore().get(A)
    assert cart.account_id == A
    assert cart.is_empty


async def test_add_then_get_round_trips() -> None:
    store = InMemoryCartStore()
    entry = new_cart_item(make_listing(), OfferType.BUY, now=NOW)

    await store.add(A, entry)

    reloaded = await store.get(A)
    assert reloaded.count == 1
    assert reloaded.find(entry.id) == entry


async def test_adding_the_same_car_twice_leaves_one_line() -> None:
    store = InMemoryCartStore()
    listing = make_listing()

    await store.add(A, new_cart_item(listing, OfferType.BUY, now=NOW))
    cart = await store.add(A, new_cart_item(listing, OfferType.BUY, now=NOW))

    assert cart.count == 1


async def test_one_accounts_cart_is_invisible_to_another() -> None:
    """Gate 14.11's property at the store layer. Asserted here as well as through the API
    because the route's account scoping is only as good as what it delegates to."""
    store = InMemoryCartStore()
    await store.add(A, new_cart_item(make_listing(), OfferType.BUY, now=NOW))

    assert (await store.get(B)).is_empty
    assert (await store.get(A)).count == 1


async def test_removing_from_one_cart_does_not_touch_another() -> None:
    store = InMemoryCartStore()
    mine = new_cart_item(make_listing(), OfferType.BUY, now=NOW)
    theirs = new_cart_item(make_listing(), OfferType.BUY, now=NOW)
    await store.add(A, mine)
    await store.add(B, theirs)

    await store.remove(A, mine.id)

    assert (await store.get(A)).is_empty
    assert (await store.get(B)).count == 1


async def test_removing_another_accounts_item_id_does_nothing() -> None:
    """The id is not a capability: knowing B's item id gets A no access to it, because the
    account is the key and the id is only looked up within it."""
    store = InMemoryCartStore()
    theirs = new_cart_item(make_listing(), OfferType.BUY, now=NOW)
    await store.add(B, theirs)

    await store.remove(A, theirs.id)

    assert (await store.get(B)).count == 1


async def test_clear_empties_only_the_named_account() -> None:
    store = InMemoryCartStore()
    await store.add(A, new_cart_item(make_listing(), OfferType.BUY, now=NOW))
    await store.add(B, new_cart_item(make_listing(), OfferType.BUY, now=NOW))

    await store.clear(A)

    assert (await store.get(A)).is_empty
    assert (await store.get(B)).count == 1
