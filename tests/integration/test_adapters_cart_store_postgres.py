"""`PostgresCartStore` -- PLAN-02 P14's durable path.

Every read goes through a **fresh store instance over a fresh sessionmaker**, which is what
"survives a process restart" actually means here (the stand-in gates 3.2/4.1/12.5 already
use). Reading back through the instance that wrote would pass against a store that never
touched Postgres at all.

The two things worth proving against real SQL rather than the dict: the `UNIQUE` natural key
turns a double-add into a no-op instead of an `IntegrityError` reaching the route (gate 14.1's
double-click), and every mutation carries `account_id` *inside* the statement so one account
cannot reach another's rows (gate 14.11, CONSTITUTION IV.4).

Skipped when `CARDINAL_DATABASE_URL` is unset, same convention as the other Postgres suites.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from src.adapters.cart_store import new_cart_item
from src.adapters.db.cart_store import PostgresCartStore
from src.adapters.db.identity_store import PostgresAccountStore
from src.adapters.db.session import dispose_engine, session_factory
from src.domain.enums import OfferType
from src.domain.identity import AccountRole
from tests.unit.helpers import make_listing

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _requires_postgres(database_url_or_skip: str) -> None:
    """The marker above is documentation; *this* is what actually skips.

    `pytest.mark.postgres` selects, it does not skip -- the skip lives in the
    `database_url_or_skip` fixture, so a module that never requests it does not skip when
    `CARDINAL_DATABASE_URL` is unset. It blocks instead, inside the driver's connect, which
    hangs the entire run rather than failing it: `make test` on a machine with no stack up
    stops dead with no indication of which test is holding it. Cheap to add, and the symptom
    it prevents is one of the more expensive ones to diagnose.
    """


@pytest.fixture(autouse=True)
async def _cleanup_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()


def _store() -> PostgresCartStore:
    return PostgresCartStore(session_factory())


async def _account() -> uuid.UUID:
    """A real account row: `cart_items.account_id` carries a foreign key, so a made-up uuid
    would fail for a reason that has nothing to do with what any of these assert."""
    accounts = PostgresAccountStore(session_factory())
    email = f"cart-{uuid.uuid4().hex[:12]}@example.com"
    await accounts.request_otp(email=email, role=AccountRole.BUYER, now=NOW)
    account, _token, _created = await accounts.verify_otp(
        email=email,
        role=AccountRole.BUYER,
        code="123456",
        full_name="Postgres Cart Buyer",
        phone="+49 170 1234567",
        profile_fields={"city": "Berlin", "country": "DE"},
        now=NOW,
    )
    return account.id


async def _seeded_listing() -> tuple[str, str]:
    """`cart_items.listing_id` is a foreign key too, so these tests need a listing that is
    really in the database. Uses whatever the seeded catalogue already holds rather than
    inserting one -- a test that seeds its own listing would be testing the seeder.

    `Listing.id` is `listing_uuid(source, source_id)` (a stable, namespaced uuid5), so the
    hand-built fixture below resolves to the *same* id as the seeded row and the foreign key
    is satisfied without this file needing to read the row's own id back."""
    from sqlalchemy import select

    from src.adapters.db.models import ListingRow

    async with session_factory()() as session:
        row = (await session.scalars(select(ListingRow).limit(1))).first()
    assert row is not None, "no listings in the database -- run `make seed` first"
    return str(row.source), str(row.source_id)


async def _item(account_id: uuid.UUID, offer_type: OfferType = OfferType.BUY):
    source, source_id = await _seeded_listing()
    listing = make_listing(source=source, source_id=source_id, offer_type=OfferType.BOTH)
    return new_cart_item(listing, offer_type, now=NOW)


# -- durability ---------------------------------------------------------------------


async def test_an_added_item_is_readable_through_a_fresh_store() -> None:
    account = await _account()
    item = await _item(account)

    await _store().add(account, item)

    reloaded = await _store().get(account)
    assert reloaded.count == 1
    line = reloaded.items[0]
    assert line.id == item.id
    assert (line.source, line.source_id) == (item.source, item.source_id)
    assert line.offer_type is item.offer_type
    assert line.added_at == item.added_at


async def test_an_empty_cart_reads_as_empty_not_as_a_miss() -> None:
    account = await _account()
    cart = await _store().get(account)
    assert cart.account_id == account
    assert cart.is_empty


# -- the unique natural key ---------------------------------------------------------


async def test_adding_the_same_car_twice_leaves_one_row() -> None:
    """The `UNIQUE (account_id, source, source_id, offer_type)` constraint is the backstop
    application logic cannot be: `Cart.with_item` can be raced, a constraint cannot."""
    account = await _account()
    first = await _item(account)
    second = await _item(account)  # same car, different row id

    await _store().add(account, first)
    cart = await _store().add(account, second)

    assert cart.count == 1, "the second add created a second line"
    assert cart.items[0].id == first.id, "the second add replaced the first instead of no-opping"


async def test_the_same_car_with_a_different_intent_is_a_second_row() -> None:
    account = await _account()
    await _store().add(account, await _item(account, OfferType.BUY))
    cart = await _store().add(account, await _item(account, OfferType.RENT))
    assert cart.count == 2


# -- account scoping (gate 14.11, inside the SQL) -----------------------------------


async def test_one_accounts_cart_is_invisible_to_another() -> None:
    mine, theirs = await _account(), await _account()
    await _store().add(mine, await _item(mine))

    assert (await _store().get(theirs)).is_empty
    assert (await _store().get(mine)).count == 1


async def test_removing_with_another_accounts_id_deletes_nothing() -> None:
    """`account_id` is in the DELETE's WHERE clause, not checked after the fact -- so this is
    unexpressible rather than merely refused."""
    mine, theirs = await _account(), await _account()
    item = await _item(mine)
    await _store().add(mine, item)

    await _store().remove(theirs, item.id)

    assert (await _store().get(mine)).count == 1


async def test_removing_my_own_item_empties_my_cart_only() -> None:
    mine, theirs = await _account(), await _account()
    item = await _item(mine)
    await _store().add(mine, item)
    await _store().add(theirs, await _item(theirs))

    await _store().remove(mine, item.id)

    assert (await _store().get(mine)).is_empty
    assert (await _store().get(theirs)).count == 1


async def test_clear_empties_only_the_named_account() -> None:
    mine, theirs = await _account(), await _account()
    await _store().add(mine, await _item(mine))
    await _store().add(theirs, await _item(theirs))

    await _store().clear(mine)

    assert (await _store().get(mine)).is_empty
    assert (await _store().get(theirs)).count == 1
