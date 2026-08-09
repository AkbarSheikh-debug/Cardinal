"""`/cart/*` through the real FastAPI app -- PLAN-02 P14.

Transport and authorisation, the same scope (and the same in-memory pinning, for the same
Windows/`ProactorEventLoop` reason) `test_api_auth.py` documents at length.

The property most of this file exists to hold down is account scoping: there is no
`account_id` anywhere in a cart route's signature, so "account A reads account B's cart" is
not a request that can be phrased. That is worth asserting anyway -- a future route that added
an id parameter for convenience would silently delete it (gate 14.11).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.adapters.db.session import ENV_DATABASE_URL
from src.api.cart import router as cart_router
from src.api.main import app


@pytest.fixture(autouse=True)
def _memory_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(ENV_DATABASE_URL, raising=False)
    yield


BUYER = {
    "email": "cart-buyer@example.com",
    "role": "buyer",
    "code": "123456",
    "full_name": "Cart Buyer",
    "phone": "+49 170 1234567",
    "profile": {"city": "Berlin", "country": "DE"},
}
OTHER_BUYER = {**BUYER, "email": "cart-buyer-2@example.com", "full_name": "Other Buyer"}
SELLER = {
    "email": "cart-seller@example.com",
    "role": "seller",
    "code": "234567",
    "full_name": "Cart Seller",
    "phone": "+49 170 7654321",
    "profile": {"role_title": "Sales Manager"},
}


def _sign_in(client: TestClient, body: dict[str, object]) -> None:
    client.post("/auth/request-otp", json={"email": body["email"], "role": body["role"]})
    verified = client.post("/auth/verify-otp", json=body)
    assert verified.status_code == 200, verified.text


def _a_listing(client: TestClient, offer_type: str = "buy") -> dict[str, str]:
    """A real listing out of the seeded catalogue, so `POST /cart/items` resolves it the way
    it would in the product rather than against a hand-written id that only exists here."""
    store = client.app.state.store  # type: ignore[attr-defined]
    listings = store.listings
    assert listings, "the in-memory store should carry the generated catalogue"
    for listing in listings:
        if listing.offer_type.value == offer_type and listing.is_available:
            return {"source": listing.source, "source_id": listing.source_id}
    raise AssertionError(f"no available {offer_type} listing in the catalogue")


# -- the shape of the API -----------------------------------------------------------


def test_there_is_no_bare_cart_route() -> None:
    """`/cart` is the *page*. Every API route lives one level down so a proxy can tell a
    navigation from a fetch by path alone -- D-076. A bare `GET /cart` reappearing here is
    exactly the regression that would make the container serve JSON where the page should be.
    """
    paths = {getattr(route, "path", None) for route in cart_router.routes}
    assert "/cart" not in paths
    assert "/cart/items" in paths
    assert all(path is None or path.startswith("/cart/") for path in paths), paths

    # And the app really does 404 it -- a route table check alone would miss a bare `/cart`
    # mounted from somewhere else entirely.
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        assert client.get("/cart").status_code == 404


# -- authentication -----------------------------------------------------------------


def test_an_anonymous_visitor_cannot_read_a_cart() -> None:
    with TestClient(app) as client:
        assert client.get("/cart/items").status_code == 401


def test_a_seller_is_refused_a_cart_with_403_not_404() -> None:
    """The same distinction gate 12.4 draws: a role refusal has to be visibly a refusal, not
    an accidental 404 that reads as "no such feature"."""
    with TestClient(app) as client:
        _sign_in(client, SELLER)
        assert client.get("/cart/items").status_code == 403


def test_the_count_endpoint_answers_zero_for_a_seller_rather_than_refusing() -> None:
    """The header badge polls this on every route. A 403 there would paint an error into a
    seller's header about a feature that simply isn't theirs."""
    with TestClient(app) as client:
        _sign_in(client, SELLER)
        response = client.get("/cart/count")
        assert response.status_code == 200
        assert response.json()["count"] == 0


# -- adding -------------------------------------------------------------------------


def test_adding_a_listing_puts_it_in_the_cart_with_its_headline_and_payee() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        listing = _a_listing(client)

        response = client.post("/cart/items", json={**listing, "offer_type": "buy"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["count"] == 1
        line = body["items"][0]
        assert line["source"] == listing["source"]
        assert line["headline"], "a line with no headline is a line the buyer can't recognise"
        assert line["available"] is True
        assert line["payee"] is not None
        assert "verification_status" in line["payee"]


def test_adding_the_same_car_twice_leaves_one_line() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        listing = _a_listing(client)

        client.post("/cart/items", json={**listing, "offer_type": "buy"})
        second = client.post("/cart/items", json={**listing, "offer_type": "buy"})

        assert second.json()["count"] == 1


def test_an_unknown_listing_is_a_404() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        response = client.post(
            "/cart/items",
            json={"source": "mock_autobazaar", "source_id": "NOPE-9999", "offer_type": "buy"},
        )
        assert response.status_code == 404


def test_an_intent_the_listing_cannot_honour_is_refused_at_the_door() -> None:
    """A rental added as a purchase would only fail at checkout, after the buyer has
    committed attention to it."""
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        rental = _a_listing(client, offer_type="rent")

        response = client.post("/cart/items", json={**rental, "offer_type": "buy"})

        assert response.status_code == 409


def test_a_missing_source_is_a_422_not_a_500() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        assert client.post("/cart/items", json={"offer_type": "buy"}).status_code == 422


def test_a_nonsense_offer_type_is_a_422() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        listing = _a_listing(client)
        response = client.post("/cart/items", json={**listing, "offer_type": "lease"})
        assert response.status_code == 422


# -- removing -----------------------------------------------------------------------


def test_removing_a_line_empties_the_cart() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        listing = _a_listing(client)
        added = client.post("/cart/items", json={**listing, "offer_type": "buy"}).json()
        item_id = added["items"][0]["item_id"]

        response = client.delete(f"/cart/items/{item_id}")

        assert response.status_code == 200
        assert response.json()["count"] == 0


def test_removing_a_non_uuid_is_a_422() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        assert client.delete("/cart/items/not-a-uuid").status_code == 422


# -- account scoping (gate 14.11) ---------------------------------------------------


def test_one_buyers_cart_is_invisible_to_another() -> None:
    with TestClient(app) as first, TestClient(app) as second:
        _sign_in(first, BUYER)
        listing = _a_listing(first)
        first.post("/cart/items", json={**listing, "offer_type": "buy"})

        _sign_in(second, OTHER_BUYER)

        assert second.get("/cart/items").json()["count"] == 0
        assert first.get("/cart/items").json()["count"] == 1


def test_knowing_another_accounts_item_id_grants_no_access_to_it() -> None:
    """The item id is not a capability. `CartStore` looks an id up *within* an account, so a
    leaked id resolves to nothing for anyone else."""
    with TestClient(app) as first, TestClient(app) as second:
        _sign_in(first, BUYER)
        listing = _a_listing(first)
        item_id = first.post("/cart/items", json={**listing, "offer_type": "buy"}).json()["items"][
            0
        ]["item_id"]

        _sign_in(second, OTHER_BUYER)
        second.delete(f"/cart/items/{item_id}")

        assert first.get("/cart/items").json()["count"] == 1, "another account removed my line"


# -- checkout hand-off --------------------------------------------------------------


def test_checkout_opens_the_booking_form_app_and_nothing_further() -> None:
    """The cart's whole job at this point is to open the front of P7/P8's existing sequence.
    It never mints a gesture token and never reaches `confirm_booking` (gate 14.6)."""
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        listing = _a_listing(client)
        item_id = client.post("/cart/items", json={**listing, "offer_type": "buy"}).json()["items"][
            0
        ]["item_id"]

        response = client.post(
            "/cart/checkout", json={"session_id": "cart-test-session", "item_id": item_id}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["opened"] is True
        assert body["resource_uri"] == "ui://booking/form"


def test_checkout_on_an_item_that_is_not_yours_is_a_404() -> None:
    with TestClient(app) as first, TestClient(app) as second:
        _sign_in(first, BUYER)
        listing = _a_listing(first)
        item_id = first.post("/cart/items", json={**listing, "offer_type": "buy"}).json()["items"][
            0
        ]["item_id"]

        _sign_in(second, OTHER_BUYER)
        response = second.post(
            "/cart/checkout", json={"session_id": "cart-test-session-2", "item_id": item_id}
        )

        assert response.status_code == 404


def test_checkout_without_a_session_id_is_a_422() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        listing = _a_listing(client)
        item_id = client.post("/cart/items", json={**listing, "offer_type": "buy"}).json()["items"][
            0
        ]["item_id"]

        assert client.post("/cart/checkout", json={"item_id": item_id}).status_code == 422
