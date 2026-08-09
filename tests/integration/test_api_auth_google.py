"""Sign in with Google -- the OAuth round trip and the seller claim step it creates.

Google itself is never called. `exchange_code`/`fetch_identity` are the only two functions
that talk to it, and both are replaced here, so these tests assert **Cardinal's** half of the
flow: the CSRF state check, where each role lands, and what the session cookie ends up being.
Testing against Google's live endpoints would need a real OAuth client, would fail on any
machine without one, and would still not exercise the parts that can actually be got wrong.

The parts that can actually be got wrong, and are pinned below:

- **The state check.** An OAuth callback that skips it is a login-CSRF: an attacker completes
  *their* Google sign-in inside *your* browser, and every action you take afterwards is on
  their account. Four separate ways to fail it are asserted.
- **Which role the account gets.** The role rides in the httpOnly cookie, never the query
  string, so a tampered callback URL cannot turn a buyer sign-in into a seller one.
- **Where a fresh seller lands.** Google carries no dealership, so a new seller must reach the
  claim step rather than an empty console that no amount of signing in again can fill (D-080).

Backend pinned to in-memory for the same reason `test_api_auth.py` pins it -- see that file's
docstring for the Windows/psycopg detail.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.adapters.db.session import ENV_DATABASE_URL
from src.adapters.oauth import google
from src.api.auth import OAUTH_STATE_COOKIE, SESSION_COOKIE
from src.api.main import app


@pytest.fixture(autouse=True)
def _memory_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(ENV_DATABASE_URL, raising=False)
    yield


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentials that look real enough for `is_configured()`, which is all any of this needs
    -- nothing here reaches the network."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)


def _stub_google(
    monkeypatch: pytest.MonkeyPatch,
    *,
    email: str = "someone@gmail.com",
    name: str = "Someone Real",
) -> None:
    """Replace the two functions that talk to Google, and only those."""

    async def fake_exchange(code: str) -> str:
        return f"access-token-for-{code}"

    async def fake_identity(access_token: str) -> google.GoogleIdentity:
        return google.GoogleIdentity(
            subject="google-subject-123",
            email=email,
            full_name=name,
            email_verified=True,
        )

    monkeypatch.setattr(google, "exchange_code", fake_exchange)
    monkeypatch.setattr(google, "fetch_identity", fake_identity)


def _start(client: TestClient, role: str = "buyer") -> str:
    """Run the start leg and return the `state` the server stored, so the callback can echo a
    value that actually matches instead of one the test invented."""
    response = client.get(f"/auth/google/start?role={role}", follow_redirects=False)
    assert response.status_code == 307, response.text
    state, _, _ = client.cookies[OAUTH_STATE_COOKIE].partition("|")
    return state


# -- what the deployment advertises -------------------------------------------------


def test_providers_reports_google_off_when_there_are_no_credentials(unconfigured: None) -> None:
    """The button is server-gated. Rendering it without a client id produces a click that
    dead-ends on Google's own error page, which the user cannot attribute to anyone."""
    with TestClient(app) as client:
        body = client.get("/auth/providers").json()
    assert body["google"] is False
    # Email sign-in survives an entirely empty environment (CONSTITUTION III.7).
    assert body["demo_otp"] is True


def test_providers_reports_google_on_once_configured(configured: None) -> None:
    with TestClient(app) as client:
        assert client.get("/auth/providers").json()["google"] is True


def test_start_refuses_when_unconfigured(unconfigured: None) -> None:
    """503 rather than a redirect: there is nowhere to redirect *to*."""
    with TestClient(app) as client:
        assert client.get("/auth/google/start", follow_redirects=False).status_code == 503


# -- the start leg ------------------------------------------------------------------


def test_start_redirects_to_google_and_stores_state_and_role(configured: None) -> None:
    with TestClient(app) as client:
        response = client.get("/auth/google/start?role=seller", follow_redirects=False)

        assert response.status_code == 307
        location = response.headers["location"]
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        # Only the scopes actually read. An app asking for more is one users should decline.
        assert "scope=openid+email+profile" in location

        cookie = client.cookies[OAUTH_STATE_COOKIE]
        state, sep, role = cookie.partition("|")
        assert sep == "|" and role == "seller"
        assert len(state) > 20, "a guessable state is not a CSRF defence"
        # The state in the cookie is the one Google is asked to echo back.
        assert f"state={state}" in location


def test_start_rejects_an_unknown_role(configured: None) -> None:
    with TestClient(app) as client:
        response = client.get("/auth/google/start?role=admin", follow_redirects=False)
    assert response.status_code == 422


# -- the callback: refusing what it should ------------------------------------------


def test_callback_without_the_cookie_is_refused(configured: None) -> None:
    """The flow did not start here -- which is exactly the login-CSRF this check exists for."""
    with TestClient(app) as client:
        response = client.get(
            "/auth/google/callback?code=abc&state=anything", follow_redirects=False
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=state_mismatch"
    assert SESSION_COOKIE not in response.cookies


def test_callback_with_a_mismatched_state_is_refused(configured: None) -> None:
    with TestClient(app) as client:
        _start(client)
        response = client.get(
            "/auth/google/callback?code=abc&state=not-the-stored-one", follow_redirects=False
        )
    assert response.headers["location"] == "/login?error=state_mismatch"
    assert SESSION_COOKIE not in response.cookies


def test_callback_without_a_code_reads_as_cancelled(configured: None) -> None:
    """The user pressed "cancel" on Google's consent screen. Not an error worth alarming about,
    but it must not produce a session either."""
    with TestClient(app) as client:
        state = _start(client)
        response = client.get(f"/auth/google/callback?state={state}", follow_redirects=False)
    assert response.headers["location"] == "/login?error=cancelled"
    assert SESSION_COOKIE not in response.cookies


def test_callback_hides_the_providers_error_detail(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Google's own error text can echo the client id back. Only a generic code leaves here."""

    async def boom(code: str) -> str:
        raise google.GoogleAuthError("invalid_client: id 123456-secret.apps.googleusercontent")

    monkeypatch.setattr(google, "exchange_code", boom)

    with TestClient(app) as client:
        state = _start(client)
        response = client.get(
            f"/auth/google/callback?code=abc&state={state}", follow_redirects=False
        )

    location = response.headers["location"]
    assert location == "/login?error=google_failed"
    assert "googleusercontent" not in location and "123456" not in location


# -- the callback: the happy paths --------------------------------------------------


def test_buyer_lands_on_the_showroom_with_a_session(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_google(monkeypatch, email="buyer@gmail.com")

    with TestClient(app) as client:
        state = _start(client, role="buyer")
        response = client.get(
            f"/auth/google/callback?code=abc&state={state}", follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert client.cookies.get(SESSION_COOKIE)

        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["account"]["email"] == "buyer@gmail.com"
        assert me.json()["account"]["role"] == "buyer"


def test_a_new_seller_is_sent_to_the_claim_step(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Google's scopes carry no dealership, so a fresh seller has none. Landing them on
    `/seller` would show a console that can never fill (D-080)."""
    _stub_google(monkeypatch, email="seller@gmail.com")

    with TestClient(app) as client:
        state = _start(client, role="seller")
        response = client.get(
            f"/auth/google/callback?code=abc&state={state}", follow_redirects=False
        )

        assert response.headers["location"] == "/login?claim=dealership"
        # Signed in regardless -- the claim step is reachable only *because* there is a session.
        assert client.get("/auth/me").status_code == 200


def test_the_role_comes_from_the_cookie_not_the_query_string(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Privilege escalation by URL edit. The start leg said `buyer`; the callback claims
    `seller`. The cookie is what counts, so the account must come out a buyer."""
    _stub_google(monkeypatch, email="tamper@gmail.com")

    with TestClient(app) as client:
        state = _start(client, role="buyer")
        client.get(
            f"/auth/google/callback?code=abc&state={state}&role=seller", follow_redirects=False
        )
        assert client.get("/auth/me").json()["account"]["role"] == "buyer"


def test_signing_in_twice_reuses_the_account(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same Google address, same Cardinal account -- not a second one with the same email."""
    _stub_google(monkeypatch, email="repeat@gmail.com")

    with TestClient(app) as client:
        first_state = _start(client)
        client.get(f"/auth/google/callback?code=one&state={first_state}", follow_redirects=False)
        first_id = client.get("/auth/me").json()["account"]["id"]

        second_state = _start(client)
        client.get(f"/auth/google/callback?code=two&state={second_state}", follow_redirects=False)
        assert client.get("/auth/me").json()["account"]["id"] == first_id


# -- the claim step -----------------------------------------------------------------


def _google_seller(client: TestClient, monkeypatch: pytest.MonkeyPatch, email: str) -> None:
    _stub_google(monkeypatch, email=email)
    state = _start(client, role="seller")
    client.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)


def _a_dealer_id(client: TestClient) -> str:
    dealers = client.get("/seller/dealers").json()
    assert dealers, "the seeded dealer directory is empty"
    return str(dealers[0]["id"])


def test_claiming_a_dealership_fills_the_profile(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(app) as client:
        _google_seller(client, monkeypatch, "claimer@gmail.com")
        dealer_id = _a_dealer_id(client)

        response = client.post("/auth/claim-dealership", json={"dealer_id": dealer_id})

        assert response.status_code == 200, response.text
        assert response.json()["claimed"] is True
        # And the session now reports it, which is what moves the seller off the claim step.
        assert client.get("/auth/me").json()["profile"]["dealer_id"] == dealer_id


def test_a_dealership_cannot_be_claimed_twice(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repair is one-shot. Left open it would be a way to move an account between
    dealerships -- and every lead with it -- from the browser console."""
    with TestClient(app) as client:
        _google_seller(client, monkeypatch, "twice@gmail.com")
        dealer_id = _a_dealer_id(client)

        first = client.post("/auth/claim-dealership", json={"dealer_id": dealer_id})
        assert first.status_code == 200
        second = client.post("/auth/claim-dealership", json={"dealer_id": dealer_id})
        assert second.status_code == 409


def test_claiming_an_unknown_dealership_is_a_404(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A well-formed uuid that names nothing would otherwise write a profile pointing at a
    dealership that does not exist -- an empty console with no visible cause."""
    with TestClient(app) as client:
        _google_seller(client, monkeypatch, "unknown@gmail.com")
        response = client.post("/auth/claim-dealership", json={"dealer_id": str(uuid.uuid4())})
    assert response.status_code == 404


def test_claiming_rejects_a_malformed_id(configured: None, monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as client:
        _google_seller(client, monkeypatch, "malformed@gmail.com")
        response = client.post("/auth/claim-dealership", json={"dealer_id": "not-a-uuid"})
    assert response.status_code == 422


def test_claiming_requires_a_signed_in_seller(configured: None) -> None:
    with TestClient(app) as client:
        response = client.post("/auth/claim-dealership", json={"dealer_id": str(uuid.uuid4())})
    assert response.status_code == 401
