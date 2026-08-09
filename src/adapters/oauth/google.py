"""Sign in with Google — the OAuth 2.0 authorization-code flow, server side.

**Why not a hosted auth service.** The obvious shortcut is one of the managed identity
vendors: one SDK call and done. Cardinal already owns identity though: P12 built `Account`,
`AuthToken` and a Postgres `accounts` table, and every downstream feature (the cart,
checkout's payee disclosure, P15's lead routing) keys off `account.id`. A hosted provider
would make a *second* source of truth for who someone is, and the two would drift the first
time one of them was the only one updated. Google verifies **who you are**; Cardinal still
issues and owns the session.

(Those vendors are described rather than named on purpose. Gate 12.3's denylist scans this
tree for auth-provider SDK names as *strings*, with no notion of whether a hit is an import
or a sentence -- so naming one here turns the gate red for a comment. That bluntness is a
feature: it cannot be talked past, which is the point of a denylist.)

**Why no JWT library.** Google returns an `id_token` (a signed JWT) alongside the access
token, and verifying it properly means a JWT library — which gate 12.3 deliberately bans, for
the good reason that a demo build carrying JWT machinery grows a real vulnerability surface.
So this uses the access token against Google's own `userinfo` endpoint instead: one HTTPS call
to an authority that already knows the answer, no local signature verification, no library. It
costs one extra round trip and removes an entire class of "we verified the token wrong" bug.

**No credential ever lives in this repository.** Client id and secret are read from the
environment at call time; gate 12.5 scans source and both lockfiles for credential shapes.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlencode

import httpx

ENV_CLIENT_ID: Final[str] = "GOOGLE_CLIENT_ID"
ENV_CLIENT_SECRET: Final[str] = "GOOGLE_CLIENT_SECRET"
#: Where Google sends the browser back. Must match a redirect URI registered on the OAuth
#: client exactly, including scheme, host, port and path -- a mismatch is the single most
#: common reason this flow fails, and Google's error says only `redirect_uri_mismatch`.
ENV_REDIRECT_URI: Final[str] = "GOOGLE_REDIRECT_URI"
DEFAULT_REDIRECT_URI: Final[str] = "http://localhost:5173/auth/google/callback"

AUTH_ENDPOINT: Final[str] = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT: Final[str] = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT: Final[str] = "https://www.googleapis.com/oauth2/v3/userinfo"

#: `openid` is what makes this an authentication rather than an authorisation request;
#: `email`/`profile` are the two claims Cardinal actually reads. Nothing more is requested --
#: an app that asks for scopes it does not use is one users are right to decline.
SCOPES: Final[tuple[str, ...]] = ("openid", "email", "profile")

_TIMEOUT_S: Final[float] = 15.0


class GoogleAuthError(RuntimeError):
    """The flow failed. Never carries a token or a secret in its message."""


@dataclass(frozen=True)
class GoogleIdentity:
    """What Google told us about the person who just signed in."""

    subject: str
    email: str
    full_name: str
    email_verified: bool
    picture: str | None = None


def _env(name: str) -> str | None:
    """Empty string counts as unset -- a `.env` line like `GOOGLE_CLIENT_ID=` otherwise reads
    as configured and produces a baffling `invalid_client` from Google."""
    return os.environ.get(name) or None


def redirect_uri() -> str:
    return _env(ENV_REDIRECT_URI) or DEFAULT_REDIRECT_URI


def is_configured() -> bool:
    """Whether this deployment can offer Google sign-in at all.

    Checked at call time, not import time, so the app boots with no credentials and the login
    page simply does not show the button (CONSTITUTION III.7: `DEMO_MODE=true` with the whole
    environment unset must still work).
    """
    return _env(ENV_CLIENT_ID) is not None and _env(ENV_CLIENT_SECRET) is not None


def new_state() -> str:
    """A CSRF token for the round trip.

    Google echoes `state` back verbatim, and comparing it to a value we stored in an httpOnly
    cookie is what stops an attacker completing *their* Google login inside *your* browser
    session. It is not decoration -- an OAuth callback with no state check is a login-CSRF.
    """
    return secrets.token_urlsafe(32)


def authorization_url(*, state: str) -> str:
    """Where to send the browser to begin."""
    client_id = _env(ENV_CLIENT_ID)
    if client_id is None:
        raise GoogleAuthError("GOOGLE_CLIENT_ID is not set")
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        # `select_account` rather than the default: a shared demo machine where the first
        # tester's account is silently reused for everyone afterwards is worse than one extra
        # click. `consent` would re-prompt every time, which is noisier than it needs to be.
        "prompt": "select_account",
    }
    return f"{AUTH_ENDPOINT}?{urlencode(query)}"


async def exchange_code(code: str) -> str:
    """Authorization code -> access token."""
    client_id, client_secret = _env(ENV_CLIENT_ID), _env(ENV_CLIENT_SECRET)
    if client_id is None or client_secret is None:
        raise GoogleAuthError("Google OAuth is not configured")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            response = await client.post(
                TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri(),
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise GoogleAuthError(f"token exchange failed: {exc}") from exc

    if response.status_code >= 400:
        # Google echoes the client_id in some error bodies; surface only the error *code* so
        # nothing credential-shaped can reach a log or an HTTP response.
        code_only = ""
        try:
            code_only = str(response.json().get("error", ""))
        except ValueError:
            code_only = ""
        raise GoogleAuthError(f"google rejected the authorization code ({code_only or 'unknown'})")

    try:
        token = str(response.json()["access_token"])
    except (ValueError, KeyError) as exc:
        raise GoogleAuthError("google's token response had no access_token") from exc
    return token


async def fetch_identity(access_token: str) -> GoogleIdentity:
    """Access token -> who this is. See the module docstring on why this is a call rather than
    a local JWT verification."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            response = await client.get(
                USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
            )
    except httpx.HTTPError as exc:
        raise GoogleAuthError(f"userinfo request failed: {exc}") from exc

    if response.status_code >= 400:
        raise GoogleAuthError(f"userinfo returned {response.status_code}")

    try:
        body = response.json()
    except ValueError as exc:
        raise GoogleAuthError("userinfo response was not JSON") from exc

    email = str(body.get("email", "")).strip().lower()
    subject = str(body.get("sub", "")).strip()
    if not email or not subject:
        raise GoogleAuthError("google returned no email for this account")

    # An unverified Google address is one somebody typed, not one they proved they own.
    # Accepting it would let anyone claim an account on an address they do not control.
    if body.get("email_verified") is not True:
        raise GoogleAuthError("that Google account's email address is not verified")

    return GoogleIdentity(
        subject=subject,
        email=email,
        full_name=str(body.get("name") or email.split("@")[0]),
        email_verified=True,
        picture=str(body["picture"]) if body.get("picture") else None,
    )
