"""Auth transport -- PLAN-02 P12. Routes only; every decision lives in
`src/adapters/identity_store.py` or `src/domain/identity.py`.

Three things here are deliberate and worth not "fixing" later without reading PLAN-02 §0.2:

- **The demo codes are returned by `request-otp`.** In a build with no SMS provider, the
  alternative is a login nobody can complete without reading the source. Returning them,
  alongside the banner, is the honest-mock posture CONSTITUTION I.5 already requires of the
  payment flow -- the failure mode to avoid is a demo that *looks* like real auth, not one
  that admits it isn't.
- **The token is an httpOnly cookie**, not a JSON field the page stores. It costs nothing
  here and it models the right thing; `Authorization: Bearer` is also accepted so gates,
  tests and non-browser clients don't need a cookie jar.
- **`/auth/verify-otp` never says whether the account already existed** in its failure
  paths, and signup and login are one route. An endpoint that answers "is this address
  registered?" to an unauthenticated caller is an account-enumeration oracle.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from src.adapters.dealer_store import DealerDirectory
from src.adapters.identity_store import AccountStore, OtpChallengeError
from src.adapters.oauth import google
from src.domain.identity import (
    DEMO_AUTH_BANNER,
    DEMO_OTP_CODES,
    TOKEN_TTL_HOURS,
    Account,
    AccountRole,
)

logger = logging.getLogger(__name__)

router = APIRouter()

#: httpOnly, so page JavaScript cannot read it; `lax` so a top-level navigation back into
#: the app keeps the session while a cross-site POST does not carry it.
SESSION_COOKIE = "cardinal_session"


def account_store(request: Request) -> AccountStore:
    store: AccountStore = request.app.state.account_store
    return store


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return request.cookies.get(SESSION_COOKIE)


async def current_account(request: Request) -> Account:
    """Resolves the caller, or 401s. The single authorisation path for every protected route.

    Unknown and expired tokens are one outcome on purpose: a caller holding a stale token
    learns it no longer works, not when it stopped or whether it ever existed.
    """
    token_value = _bearer(request)
    if not token_value:
        raise HTTPException(status_code=401, detail="not signed in")
    store = account_store(request)
    token = await store.resolve_token(token_value)
    if token is None:
        raise HTTPException(status_code=401, detail="not signed in")
    account = await store.get_account(token.account_id)
    if account is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return account


async def require_role(request: Request, role: AccountRole) -> Account:
    """403, not 404: the caller is authenticated, they simply are not this role.

    Returning 404 here would be security theatre -- it hides nothing from someone who
    already knows the route exists, and it makes a genuine routing bug indistinguishable
    from a permission denial in the logs.
    """
    account = await current_account(request)
    if account.role is not role:
        raise HTTPException(status_code=403, detail=f"this route is for {role.value} accounts")
    return account


def _role_from(body: dict[str, Any]) -> AccountRole:
    try:
        return AccountRole(str(body.get("role", "")).strip().lower())
    except ValueError:
        raise HTTPException(status_code=422, detail="role must be 'buyer' or 'seller'") from None


def _account_payload(account: Account) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "role": account.role.value,
        "email": account.email,
        "full_name": account.full_name,
        "phone": account.phone,
        "created_at": account.created_at.isoformat(),
    }


async def _validate_dealer_claim(request: Request, profile_fields: dict[str, Any]) -> None:
    """A seller says which dealership they represent at signup; this checks it is a real one.

    PLAN-02 P13 listed "`SellerProfile.dealer_id` populated" in its scope and P13 shipped
    without it -- nothing set the field, so every seller account had `dealer_id=None` and
    P15's lead routing would have had nothing to route *to*. This is where it gets set, and
    the claim is validated rather than trusted: an unknown id would produce an account whose
    console is permanently, silently empty, which is the worst way to learn about a typo.

    Deliberately **not** an authorisation check. With demo auth anyone may claim any
    dealership, and pretending otherwise would be exactly the kind of security theatre
    PLAN-02 §0.2 rules out. Real provisioning is `[SCALE]`; this is the seam it replaces.
    """
    claimed = profile_fields.get("dealer_id")
    if claimed in (None, ""):
        return
    try:
        dealer_id = uuid.UUID(str(claimed))
    except ValueError:
        raise HTTPException(status_code=422, detail="dealer_id must be a uuid") from None
    directory: DealerDirectory = request.app.state.dealers
    if await directory.get(dealer_id) is None:
        raise HTTPException(status_code=422, detail="no such dealership")


@router.post("/auth/request-otp")
async def request_otp(request: Request) -> dict[str, Any]:
    """Starts a login. Always succeeds for a well-formed address -- see the module docstring
    on why this must not reveal whether the account exists."""
    body = await request.json()
    email = str(body.get("email", "")).strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="a valid email is required")
    role = _role_from(body)

    challenge = await account_store(request).request_otp(email=email, role=role)
    return {
        "email": challenge.email,
        "role": role.value,
        "expires_at": challenge.expires_at.isoformat(),
        "banner": DEMO_AUTH_BANNER,
        #: Honest mock (CONSTITUTION I.5). There is no channel to deliver these on.
        "demo_codes": list(DEMO_OTP_CODES),
    }


@router.post("/auth/verify-otp")
async def verify_otp(request: Request, response: Response) -> dict[str, Any]:
    """Completes a login, creating the account on first use. Signup and login are one
    gesture -- which is what the demo needs and what keeps this route from leaking which
    addresses are registered."""
    body = await request.json()
    email = str(body.get("email", "")).strip()
    role = _role_from(body)
    code = str(body.get("code", ""))
    full_name = str(body.get("full_name", "")).strip()
    phone = str(body.get("phone", "")).strip()
    profile_fields = body.get("profile") or {}
    if not isinstance(profile_fields, dict):
        raise HTTPException(status_code=422, detail="profile must be an object")
    if role is AccountRole.SELLER:
        await _validate_dealer_claim(request, profile_fields)

    try:
        account, token, created = await account_store(request).verify_otp(
            email=email,
            role=role,
            code=code,
            full_name=full_name,
            phone=phone,
            profile_fields=profile_fields,
        )
    except OtpChallengeError as exc:
        # One status and one message for "wrong code" and "no challenge" alike.
        raise HTTPException(status_code=401, detail=str(exc)) from None
    except ValueError as exc:
        # Pydantic rejected the name/phone/profile -- a 422 with the reason, since the
        # caller supplied all of it and can fix it.
        raise HTTPException(status_code=422, detail=str(exc)) from None

    response.set_cookie(
        SESSION_COOKIE,
        token.token,
        httponly=True,
        samesite="lax",
        max_age=TOKEN_TTL_HOURS * 3600,
        path="/",
    )
    return {"account": _account_payload(account), "created": created, "token": token.token}


@router.get("/auth/me")
async def me(request: Request) -> dict[str, Any]:
    """The caller's own account and profile.

    This is the *only* route that returns `annual_income`, and it returns it to the person
    who entered it (PLAN-02 §0.3). Nothing seller-facing ever includes it.
    """
    account = await current_account(request)
    store = account_store(request)
    if account.role is AccountRole.SELLER:
        seller = await store.get_seller_profile(account.id)
        profile = seller.model_dump(mode="json") if seller else None
    else:
        buyer = await store.get_buyer_profile(account.id)
        profile = buyer.model_dump(mode="json") if buyer else None
    return {"account": _account_payload(account), "profile": profile}


@router.post("/auth/logout")
async def logout(request: Request, response: Response) -> dict[str, Any]:
    token_value = _bearer(request)
    if token_value:
        await account_store(request).revoke_token(token_value)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"signed_out": True}


#: Carries the CSRF `state` *and* the role across the Google round trip. httpOnly, short-lived
#: and `lax` -- Google's callback is a top-level GET navigation, which `lax` permits and
#: `strict` would silently drop, leaving every sign-in failing the state check.
OAUTH_STATE_COOKIE = "cardinal_oauth"
OAUTH_STATE_TTL_S = 10 * 60


@router.get("/auth/providers")
async def providers() -> dict[str, Any]:
    """What sign-in methods this deployment can actually offer.

    The button is only shown when the server says so. Rendering "Continue with Google" on a
    build with no client id produces a click that dead-ends at Google's own error page --
    worse than not offering it, because the user cannot tell whose fault it is.
    """
    return {
        "google": google.is_configured(),
        # Always true: the demo OTP codes are constants, so email sign-in works with the
        # entire environment unset (CONSTITUTION III.7).
        "demo_otp": True,
    }


@router.get("/auth/google/start")
async def google_start(request: Request, role: str = "buyer") -> Response:
    """Begin the flow. Redirects the browser to Google."""
    if not google.is_configured():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        parsed_role = AccountRole(role.strip().lower())
    except ValueError:
        raise HTTPException(status_code=422, detail="role must be 'buyer' or 'seller'") from None

    state = google.new_state()
    response = RedirectResponse(google.authorization_url(state=state), status_code=307)
    # `state|role` in one httpOnly cookie: the role has to survive the round trip too, and
    # putting it in the URL would let someone flip a buyer sign-in into a seller one by
    # editing the callback query string.
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        f"{state}|{parsed_role.value}",
        httponly=True,
        samesite="lax",
        max_age=OAUTH_STATE_TTL_S,
        path="/",
    )
    return response


@router.get("/auth/google/callback")
async def google_callback(request: Request, code: str = "", state: str = "") -> Response:
    """Where Google sends the browser back.

    Ends in a redirect rather than JSON: this is a top-level navigation, so the user must land
    on a page. Failures redirect to `/login?error=...` for the same reason -- a JSON body here
    would render as raw text in the address bar.
    """
    stored = request.cookies.get(OAUTH_STATE_COOKIE, "")
    expected_state, _, role_value = stored.partition("|")

    # Constant-time compare, and both halves must be present. A missing cookie means the flow
    # did not start here -- which is exactly the login-CSRF this check exists to refuse.
    if not expected_state or not state or not secrets.compare_digest(state, expected_state):
        return _login_redirect("state_mismatch")
    if not code:
        return _login_redirect("cancelled")

    try:
        role = AccountRole(role_value)
    except ValueError:
        return _login_redirect("state_mismatch")

    try:
        identity = await google.fetch_identity(await google.exchange_code(code))
    except google.GoogleAuthError:
        # Deliberately not surfaced verbatim: the provider's message can echo the client id.
        return _login_redirect("google_failed")

    account, token, created = await account_store(request).sign_in_external(
        email=identity.email,
        role=role,
        full_name=identity.full_name,
        # Google's email/profile scopes carry no phone; checkout collects it when needed.
        phone="",
        # Empty for both roles. Google supplies none of the profile either side needs, and
        # every field it does not supply is left unset rather than defaulted -- see the note
        # on `BuyerProfile.city` for why an invented city is worse than a missing one.
        profile_fields={},
    )

    # A brand-new seller has no dealership yet -- they never saw the picker. Send them to the
    # claim step rather than to a console that can never fill (the stuck state D-080 warns
    # about, which `POST /auth/claim-dealership` now also repairs).
    destination = "/"
    if role is AccountRole.SELLER:
        profile = await account_store(request).get_seller_profile(account.id)
        destination = "/seller" if profile and profile.dealer_id else "/login?claim=dealership"

    response = RedirectResponse(destination, status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        token.token,
        httponly=True,
        samesite="lax",
        max_age=TOKEN_TTL_HOURS * 3600,
        path="/",
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    logger.info("google sign-in ok (created=%s, role=%s)", created, role.value)
    return response


def _login_redirect(error: str) -> Response:
    response = RedirectResponse(f"/login?error={error}", status_code=303)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return response


@router.post("/auth/claim-dealership")
async def claim_dealership(request: Request) -> dict[str, Any]:
    """Attach a dealership to a seller who has none.

    Only valid while the account has no dealership (`AccountStore.claim_dealership` enforces
    it). That covers the Google seller who never saw the picker, and repairs any account
    created before the signup form made it required -- which was otherwise a permanent dead
    end, since the profile is written once at signup.
    """
    account = await require_role(request, AccountRole.SELLER)
    body = await request.json()
    try:
        dealer_id = uuid.UUID(str(body.get("dealer_id", "")))
    except ValueError:
        raise HTTPException(status_code=422, detail="dealer_id must be a uuid") from None

    directory: DealerDirectory = request.app.state.dealers
    if await directory.get(dealer_id) is None:
        raise HTTPException(status_code=404, detail="no such dealership")

    try:
        profile = await account_store(request).claim_dealership(account.id, dealer_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"claimed": True, "profile": profile.model_dump(mode="json")}


@router.get("/seller/profile")
async def seller_profile(request: Request) -> dict[str, Any]:
    """The seller's own account view, and P12's first role-guarded route.

    It exists now rather than in P15 so `require_role` has something real to protect and
    gate 12.4 is a genuine assertion rather than a promise about routes that don't exist
    yet. P15's lead routes mount behind the identical guard.
    """
    account = await require_role(request, AccountRole.SELLER)
    profile = await account_store(request).get_seller_profile(account.id)
    return {
        "account": _account_payload(account),
        "profile": profile.model_dump(mode="json") if profile else None,
    }
