"""`/auth/*` and the role guard, through the real FastAPI app -- PLAN-02 P12.

These are transport and authorisation tests: what a route returns for a given caller.
Persistence is `test_adapters_identity_store_postgres.py`'s question, and it asks it against
real Postgres. So the backend is pinned to in-memory here regardless of the environment --
which is also the same path `DEMO_MODE` takes, so these exercise the configuration a judge
on a clean machine actually runs.

Pinning it is not just tidiness: on native Windows `TestClient` drives the app on a
`ProactorEventLoop`, and psycopg's async mode refuses that loop outright (the interaction
PROGRESS.md already records for gate 8). Without the fixture below, every test in this file
fails with an `InterfaceError` the moment `CARDINAL_DATABASE_URL` happens to be set -- for a
reason that has nothing to do with what any of them assert.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.adapters.db.session import ENV_DATABASE_URL
from src.api.auth import SESSION_COOKIE
from src.api.main import app
from src.domain.identity import DEMO_OTP_CODES


@pytest.fixture(autouse=True)
def _memory_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Popped before `TestClient(app)` runs lifespan, which is where the store is built."""
    monkeypatch.delenv(ENV_DATABASE_URL, raising=False)
    yield


BUYER = {
    "email": "buyer@example.com",
    "role": "buyer",
    "code": "123456",
    "full_name": "Test Buyer",
    "phone": "+49 170 1234567",
    "profile": {"city": "Berlin", "country": "DE"},
}
SELLER = {
    "email": "seller@example.com",
    "role": "seller",
    "code": "234567",
    "full_name": "Test Seller",
    "phone": "+49 170 7654321",
    "profile": {"role_title": "Sales Manager"},
}


def _sign_in(client: TestClient, body: dict[str, object]) -> dict:
    started = client.post("/auth/request-otp", json={"email": body["email"], "role": body["role"]})
    assert started.status_code == 200, started.text
    verified = client.post("/auth/verify-otp", json=body)
    assert verified.status_code == 200, verified.text
    return verified.json()


# -- the flow -----------------------------------------------------------------------


def test_request_otp_returns_the_demo_codes_and_the_banner() -> None:
    """The honest-mock posture (CONSTITUTION I.5): there is no channel to deliver a code on,
    so the route says so rather than pretending one exists."""
    with TestClient(app) as client:
        response = client.post(
            "/auth/request-otp", json={"email": "someone@example.com", "role": "buyer"}
        )
        body = response.json()
        assert body["demo_codes"] == list(DEMO_OTP_CODES)
        assert "NOT REAL SECURITY" in body["banner"]


def test_a_first_login_creates_the_account_and_sets_an_httponly_cookie() -> None:
    with TestClient(app) as client:
        client.post("/auth/request-otp", json={"email": BUYER["email"], "role": BUYER["role"]})
        verified = client.post("/auth/verify-otp", json=BUYER)

        body = verified.json()
        assert body["created"] is True
        assert body["account"]["email"] == "buyer@example.com"
        assert body["account"]["role"] == "buyer"
        assert client.cookies.get(SESSION_COOKIE)
        # httpOnly is what stops page JavaScript reading the session (PLAN-02 §0.2).
        # Asserted on *this* response: the challenge is single-use, so re-posting the same
        # body just to inspect its headers would (correctly) 401 instead.
        assert "httponly" in verified.headers.get("set-cookie", "").lower()


def test_me_returns_the_signed_in_account_and_profile() -> None:
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        response = client.get("/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert body["account"]["full_name"] == "Test Buyer"
        assert body["profile"]["city"] == "Berlin"
        assert body["profile"]["income_band"] == "undisclosed"


def test_a_bearer_token_works_without_a_cookie_jar() -> None:
    with TestClient(app) as client:
        token = _sign_in(client, BUYER)["token"]
        # Deliberately not a second `TestClient`: that re-runs lifespan, rebuilding
        # `app.state.account_store` and legitimately forgetting every live login. Clearing
        # the jar isolates the thing actually under test -- the header alone carries it.
        client.cookies.clear()
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["account"]["email"] == "buyer@example.com"


def test_logout_revokes_the_token() -> None:
    with TestClient(app) as client:
        token = _sign_in(client, BUYER)["token"]
        assert client.post("/auth/logout").status_code == 200
        after = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert after.status_code == 401


# -- refusals -----------------------------------------------------------------------


def test_me_without_a_session_is_401() -> None:
    with TestClient(app) as client:
        assert client.get("/auth/me").status_code == 401


def test_a_wrong_code_is_401() -> None:
    with TestClient(app) as client:
        client.post("/auth/request-otp", json={"email": "x@example.com", "role": "buyer"})
        response = client.post(
            "/auth/verify-otp", json={**BUYER, "email": "x@example.com", "code": "999999"}
        )
        assert response.status_code == 401


def test_verify_without_request_is_401() -> None:
    with TestClient(app) as client:
        response = client.post("/auth/verify-otp", json={**BUYER, "email": "never@example.com"})
        assert response.status_code == 401


def test_the_two_failure_modes_are_indistinguishable_to_the_caller() -> None:
    """No account-enumeration oracle: "wrong code" and "no such login" answer identically."""
    with TestClient(app) as client:
        client.post("/auth/request-otp", json={"email": "known@example.com", "role": "buyer"})
        wrong_code = client.post(
            "/auth/verify-otp", json={**BUYER, "email": "known@example.com", "code": "999999"}
        )
        no_challenge = client.post(
            "/auth/verify-otp", json={**BUYER, "email": "unknown@example.com"}
        )
        assert wrong_code.status_code == no_challenge.status_code == 401
        assert wrong_code.json()["detail"] == no_challenge.json()["detail"]


def test_a_malformed_role_is_422() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/auth/request-otp", json={"email": "x@example.com", "role": "administrator"}
        )
        assert response.status_code == 422


def test_a_malformed_email_is_422() -> None:
    with TestClient(app) as client:
        response = client.post("/auth/request-otp", json={"email": "not-an-email", "role": "buyer"})
        assert response.status_code == 422


def test_a_malformed_phone_is_422_not_500() -> None:
    """Pydantic's rejection has to surface as a client error, not an unhandled exception."""
    with TestClient(app) as client:
        client.post("/auth/request-otp", json={"email": "p@example.com", "role": "buyer"})
        response = client.post(
            "/auth/verify-otp", json={**BUYER, "email": "p@example.com", "phone": "nope"}
        )
        assert response.status_code == 422


# -- the role guard (gate 12.4) ------------------------------------------------------


def test_a_seller_reaches_the_seller_route() -> None:
    with TestClient(app) as client:
        _sign_in(client, SELLER)
        response = client.get("/seller/profile")
        assert response.status_code == 200
        assert response.json()["account"]["role"] == "seller"


def test_a_buyer_token_cannot_read_a_seller_route() -> None:
    """Gate 12.4. 403 and not 404 -- the caller is authenticated, they are the wrong role."""
    with TestClient(app) as client:
        _sign_in(client, BUYER)
        response = client.get("/seller/profile")
        assert response.status_code == 403


def test_an_anonymous_caller_cannot_read_a_seller_route() -> None:
    with TestClient(app) as client:
        assert client.get("/seller/profile").status_code == 401


# -- privacy (gates 12.6 / 12.7 read the same fields) --------------------------------


def test_exact_income_round_trips_to_its_owner_and_the_band_is_derived() -> None:
    with TestClient(app) as client:
        _sign_in(
            client,
            {
                **BUYER,
                "email": "rich@example.com",
                "profile": {
                    "city": "Munich",
                    "country": "DE",
                    "annual_income": {"amount": "120000", "currency": "EUR"},
                },
            },
        )
        profile = client.get("/auth/me").json()["profile"]
        assert profile["annual_income"]["amount"] == "120000.00"
        assert profile["income_band"] == "100k_plus"


def test_a_crafted_income_band_in_the_request_body_is_ignored() -> None:
    """Gate 12.8 end to end: the band is derived server-side or it is nothing."""
    with TestClient(app) as client:
        _sign_in(
            client,
            {
                **BUYER,
                "email": "liar@example.com",
                "profile": {
                    "city": "Berlin",
                    "country": "DE",
                    "annual_income": None,
                    "income_band": "100k_plus",
                },
            },
        )
        assert client.get("/auth/me").json()["profile"]["income_band"] == "undisclosed"


def test_the_seller_route_never_returns_income_fields() -> None:
    """P15's privacy rule, asserted the moment a seller-facing route exists at all."""
    with TestClient(app) as client:
        _sign_in(client, SELLER)
        body = client.get("/seller/profile").text
        assert "annual_income" not in body
        assert "income_band" not in body
