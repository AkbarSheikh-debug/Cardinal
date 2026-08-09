"""`src/domain/cart.py` -- PLAN-02 P14.

Pure pydantic, so these run with no event loop, no store and no clock. The two rules the
module's docstring states are the two things worth asserting hardest: adding the same car
twice is idempotent rather than a quantity of two, and every mutation returns a new `Cart`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domain.cart import Cart, CartItem
from src.domain.enums import OfferType

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
ACCOUNT = uuid.UUID("11111111-1111-1111-1111-111111111111")


def item(
    source: str = "mock_autobazaar",
    source_id: str = "AB-1073",
    offer_type: OfferType = OfferType.BUY,
) -> CartItem:
    return CartItem(
        id=uuid.uuid4(),
        listing_id=uuid.uuid4(),
        source=source,
        source_id=source_id,
        offer_type=offer_type,
        added_at=NOW,
    )


# -- identity -----------------------------------------------------------------------


def test_natural_key_is_source_source_id_and_offer_type() -> None:
    assert item().natural_key == ("mock_autobazaar", "AB-1073", OfferType.BUY)


def test_the_same_car_to_buy_and_to_rent_are_two_different_items() -> None:
    """Intent is part of the identity, not a detail hanging off it: comparing "rent this for
    six months" against "buy this" is a perfectly ordinary thing to want in one cart."""
    assert item(offer_type=OfferType.BUY).natural_key != item(offer_type=OfferType.RENT).natural_key


def test_an_item_is_frozen() -> None:
    with pytest.raises(ValidationError):
        item().source = "somewhere_else"  # type: ignore[misc]


# -- with_item ----------------------------------------------------------------------


def test_adding_a_car_puts_it_in_the_cart() -> None:
    cart = Cart(account_id=ACCOUNT).with_item(item())
    assert cart.count == 1
    assert not cart.is_empty


def test_adding_the_same_car_twice_is_a_no_op_not_a_quantity_of_two() -> None:
    """Every listing is one physical vehicle. A cart holding two of `AB-1073` describes
    something that does not exist, and the checkout it produces is priced for a car that
    isn't there."""
    first = Cart(account_id=ACCOUNT).with_item(item())
    second = first.with_item(item())  # a different item id, the same car

    assert second.count == 1
    assert second is first, "an idempotent add should return the very same cart"


def test_the_same_car_with_a_different_intent_is_a_second_line() -> None:
    cart = Cart(account_id=ACCOUNT).with_item(item(offer_type=OfferType.BUY))
    cart = cart.with_item(item(offer_type=OfferType.RENT))
    assert cart.count == 2


def test_adding_does_not_mutate_the_cart_it_was_called_on() -> None:
    empty = Cart(account_id=ACCOUNT)
    empty.with_item(item())
    assert empty.count == 0


# -- lookup and removal -------------------------------------------------------------


def test_find_returns_the_item_by_id_and_none_for_a_stranger() -> None:
    entry = item()
    cart = Cart(account_id=ACCOUNT).with_item(entry)
    assert cart.find(entry.id) == entry
    assert cart.find(uuid.uuid4()) is None


def test_contains_asks_by_natural_key_not_by_id() -> None:
    cart = Cart(account_id=ACCOUNT).with_item(item())
    assert cart.contains("mock_autobazaar", "AB-1073", OfferType.BUY)
    assert not cart.contains("mock_autobazaar", "AB-1073", OfferType.RENT)
    assert not cart.contains("mock_drivenow", "AB-1073", OfferType.BUY)


def test_removing_an_item_leaves_the_others_alone() -> None:
    first, second = item(source_id="AB-1"), item(source_id="AB-2")
    cart = Cart(account_id=ACCOUNT).with_item(first).with_item(second)

    remaining = cart.without_item(first.id)

    assert remaining.count == 1
    assert remaining.find(second.id) is not None


def test_removing_an_item_that_is_not_there_is_not_an_error() -> None:
    """`DELETE /cart/items/{id}` is idempotent from the buyer's side -- a double-clicked
    Remove should not produce a 404 for a line that is already gone."""
    cart = Cart(account_id=ACCOUNT).with_item(item())
    assert cart.without_item(uuid.uuid4()).count == 1


def test_clearing_empties_the_cart_but_keeps_the_account() -> None:
    cart = Cart(account_id=ACCOUNT).with_item(item()).cleared()
    assert cart.is_empty
    assert cart.account_id == ACCOUNT
