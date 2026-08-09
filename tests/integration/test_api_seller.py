"""`/seller/*` and the lead-creation seam, through the real FastAPI app -- PLAN-02 P15.

Transport, authorisation and privacy. Persistence is
`test_adapters_lead_store_postgres.py`'s question; the backend is pinned to in-memory here
for the reason `test_api_auth.py` documents at length (and the same Windows event-loop
interaction).

The privacy assertions are the point of this file: a browsing buyer produces nothing, a seller
never sees another seller's leads, and no income-shaped field reaches any seller-facing byte.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.adapters.db.session import ENV_DATABASE_URL
from src.api.main import app
from src.api.seller import router as seller_router


@pytest.fixture(autouse=True)
def _memory_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(ENV_DATABASE_URL, raising=False)
    yield


BUYER = {
    "email": "lead-buyer@example.com",
    "role": "buyer",
    "code": "123456",
    "full_name": "Bea Buyer",
    "phone": "+49 170 1234567",
    "profile": {
        "city": "Berlin",
        "country": "DE",
        # Deliberately present: every seller-facing assertion below is only meaningful if the
        # buyer actually has income on file to leak.
        "annual_income": {"amount": "88000", "currency": "EUR"},
        "employer": "Contoso GmbH",
    },
}
OTHER_BUYER = {**BUYER, "email": "lead-buyer-2@example.com", "full_name": "Ben Buyer"}


def _sign_in(client: TestClient, body: dict[str, object]) -> None:
    client.post("/auth/request-otp", json={"email": body["email"], "role": body["role"]})
    verified = client.post("/auth/verify-otp", json=body)
    assert verified.status_code == 200, verified.text


def _listing(client: TestClient, *, dealer_not: str | None = None):
    for listing in client.app.state.store.listings:  # type: ignore[attr-defined]
        if not (listing.offer_type.is_buyable and listing.is_available and listing.dealer_id):
            continue
        if dealer_not is not None and str(listing.dealer_id) == dealer_not:
            continue
        return listing
    raise AssertionError("no suitable listing in the catalogue")


def _sign_in_seller(
    client: TestClient, dealer_id: str, email: str = "lead-seller@example.com"
) -> None:
    body = {
        "email": email,
        "role": "seller",
        "code": "234567",
        "full_name": "Sam Seller",
        "phone": "+49 170 7654321",
        "profile": {"role_title": "Sales Manager", "dealer_id": dealer_id},
    }
    _sign_in(client, body)


# -- the shape of the API ------------------------------------------------------------


def test_no_seller_route_is_the_bare_page_path() -> None:
    """`/seller` is the *page*; every API route lives one level down so a proxy can tell a
    navigation from a fetch by path alone (D-076)."""
    paths = {getattr(route, "path", None) for route in seller_router.routes}
    assert "/seller" not in paths
    assert paths >= {"/seller/leads", "/seller/events", "/seller/dealers"}


def test_the_dealer_picker_is_public_and_carries_nothing_account_shaped() -> None:
    with TestClient(app) as client:
        response = client.get("/seller/dealers")
        assert response.status_code == 200
        options = response.json()
        assert len(options) > 10
        assert set(options[0]) == {"id", "display_name", "city", "country", "verified"}


# -- authorisation -------------------------------------------------------------------


def test_an_anonymous_visitor_cannot_read_leads() -> None:
    with TestClient(app) as client:
        assert client.get("/seller/leads").status_code == 401


def test_a_buyer_cannot_read_leads() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        assert client.get("/seller/leads").status_code == 403


def test_a_seller_with_no_dealership_gets_a_clear_409_not_an_empty_list() -> None:
    """ "You have no leads" and "your account was never linked to a dealership" are different
    problems, and answering the second with the first costs somebody an afternoon."""
    with TestClient(app) as client:
        _sign_in(
            client,
            {
                "email": "unlinked@example.com",
                "role": "seller",
                "code": "234567",
                "full_name": "Unlinked Seller",
                "phone": "+49 170 0000000",
                "profile": {"role_title": "Sales"},
            },
        )
        response = client.get("/seller/leads")
        assert response.status_code == 409
        assert "dealership" in response.json()["detail"]


def test_claiming_a_dealership_that_does_not_exist_is_rejected_at_signup() -> None:
    with TestClient(app) as client:
        client.post("/auth/request-otp", json={"email": "ghost@example.com", "role": "seller"})
        response = client.post(
            "/auth/verify-otp",
            json={
                "email": "ghost@example.com",
                "role": "seller",
                "code": "234567",
                "full_name": "Ghost Seller",
                "phone": "+49 170 0000000",
                "profile": {"dealer_id": "00000000-0000-0000-0000-000000000000"},
            },
        )
        assert response.status_code == 422
        assert "dealership" in response.json()["detail"]


# -- lead creation (gate 15.1) -------------------------------------------------------


def test_a_cart_add_creates_one_lead_routed_to_the_cars_dealer() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        body = seller.get("/seller/leads").json()

        assert len(body["leads"]) == 1
        lead = body["leads"][0]
        assert lead["source_id"] == listing.source_id
        assert lead["events"] == ["cart_add"]


def test_a_second_action_on_the_same_car_updates_the_one_lead() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        added = buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        ).json()
        buyer.post(
            "/cart/checkout",
            json={"session_id": "seller-test", "item_id": added["items"][0]["item_id"]},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        leads = seller.get("/seller/leads").json()["leads"]

        assert len(leads) == 1
        assert set(leads[0]["events"]) == {"cart_add", "checkout_opened"}


def test_opening_checkout_raises_the_tier_above_a_bare_cart_add() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        added = buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        ).json()

        _sign_in_seller(seller, str(listing.dealer_id))
        before = seller.get("/seller/leads").json()["leads"][0]["score"]

        buyer.post(
            "/cart/checkout",
            json={"session_id": "seller-test", "item_id": added["items"][0]["item_id"]},
        )
        after = seller.get("/seller/leads").json()["leads"][0]["score"]

        assert after > before


# -- browsing produces nothing (gate 15.6) -------------------------------------------


def test_a_buyer_who_only_signed_in_produces_no_lead() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        # No cart-add, no checkout, no booking form. Just a session.
        buyer.get("/cart/items")
        buyer.get("/auth/me")

        _sign_in_seller(seller, str(listing.dealer_id))
        body = seller.get("/seller/leads").json()

        assert body["leads"] == []
        assert BUYER["email"] not in seller.get("/seller/leads").text


# -- cross-seller isolation (gate 15.5) ----------------------------------------------


def test_one_seller_never_sees_another_sellers_leads() -> None:
    with TestClient(app) as buyer, TestClient(app) as mine, TestClient(app) as theirs:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        other = _listing(buyer, dealer_not=str(listing.dealer_id))
        _sign_in_seller(mine, str(listing.dealer_id), email="mine@example.com")
        _sign_in_seller(theirs, str(other.dealer_id), email="theirs@example.com")

        assert len(mine.get("/seller/leads").json()["leads"]) == 1
        assert theirs.get("/seller/leads").json()["leads"] == []


def test_marking_another_dealers_lead_contacted_is_a_404() -> None:
    with TestClient(app) as buyer, TestClient(app) as mine, TestClient(app) as theirs:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )
        _sign_in_seller(mine, str(listing.dealer_id), email="mine2@example.com")
        lead_id = mine.get("/seller/leads").json()["leads"][0]["id"]

        other = _listing(buyer, dealer_not=str(listing.dealer_id))
        _sign_in_seller(theirs, str(other.dealer_id), email="theirs2@example.com")

        assert theirs.post(f"/seller/leads/{lead_id}/contacted").status_code == 404
        assert mine.get("/seller/leads").json()["leads"][0]["state"] == "new"


# -- privacy (gate 15.7) -------------------------------------------------------------


def test_no_income_shaped_field_reaches_a_seller() -> None:
    """The buyer above has an exact income and an employer on file. Neither, nor the derived
    band, may appear anywhere in a seller-facing byte -- asserted on the raw response text so
    a nested field cannot hide from a key check."""
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        text = seller.get("/seller/leads").text.lower()

        for term in ("income", "band", "88000", "employer", "contoso", "salary"):
            assert term not in text, f"{term!r} reached a seller-facing payload"


def test_contact_details_are_released_because_an_intent_action_happened() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        lead = seller.get("/seller/leads").json()["leads"][0]

        assert lead["buyer"]["full_name"] == BUYER["full_name"]
        assert lead["buyer"]["email"] == BUYER["email"]
        assert lead["buyer"]["phone"] == BUYER["phone"]
        assert set(lead["buyer"]) == {"full_name", "email", "phone"}


# -- the payload's own guarantees ----------------------------------------------------


def test_every_tier_is_phrased_as_an_estimate_with_its_reasoning() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        lead = seller.get("/seller/leads").json()["leads"][0]

        assert "(estimated)" in lead["tier_label"]
        assert lead["explanation"].startswith(lead["tier_label"])
        assert lead["guidance"]


def test_signal_contributions_sum_to_the_score() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        lead = seller.get("/seller/leads").json()["leads"][0]

        assert abs(lead["score"] - sum(s["contribution"] for s in lead["signals"])) < 1e-9
        assert all(s["explanation"] for s in lead["signals"])


def test_a_lead_names_the_car_in_words_a_salesperson_can_use() -> None:
    """`mock_autobazaar:AB-1001` is not something anyone can phone a buyer about. The
    headline and the *current* price are resolved on read, so a lead never quotes a stale
    figure -- and the raw reference stays alongside, because it is what a dealer searches on.
    """
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        lead = seller.get("/seller/leads").json()["leads"][0]

        assert lead["listing"] is not None
        assert str(listing.year) in lead["listing"]["headline"]
        assert listing.brand in lead["listing"]["headline"]
        assert lead["listing"]["price"]["currency"] == "EUR"
        assert lead["listing"]["available"] is True
        # A small projection, not a dumped entity (D-026's reasoning).
        assert set(lead["listing"]) == {"headline", "price", "condition", "available"}
        # And the raw reference is still there to search on.
        assert lead["source_id"] == listing.source_id


def test_marking_contacted_moves_the_state() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        lead_id = seller.get("/seller/leads").json()["leads"][0]["id"]

        assert seller.post(f"/seller/leads/{lead_id}/contacted").json()["state"] == "contacted"
        assert seller.get("/seller/leads").json()["leads"][0]["state"] == "contacted"


def test_the_analytics_strip_counts_by_tier() -> None:
    with TestClient(app) as buyer, TestClient(app) as seller:
        listing = _listing(buyer)
        _sign_in(buyer, BUYER)
        buyer.post(
            "/cart/items",
            json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
        )

        _sign_in_seller(seller, str(listing.dealer_id))
        analytics = seller.get("/seller/leads").json()["analytics"]

        assert analytics["total"] == 1
        assert sum(analytics["by_tier"].values()) == 1
        assert len(analytics["by_day"]) == 7
