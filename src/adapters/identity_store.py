"""Where accounts, profiles and session tokens live -- the same protocol/in-memory/Postgres
split `src/adapters/booking_store.py` makes for bookings.

Three things live here rather than in `src/domain` because each one needs something the
domain is not allowed to touch:

- **Token minting** reads `secrets`, which is non-deterministic. `AuthToken` itself (a pure
  model with `is_valid_at(now)`) stays in the domain; only the minting is here.
- **The clock.** Every method that stamps a time takes `now` with a `datetime.now(UTC)`
  default, so tests and gates can pin it and production doesn't have to pass it.
- **The OTP challenge.** `request_otp` records that a login was actually started, so
  `verify_otp` can refuse a code for a flow nobody began. In a demo build the codes are
  fixed (PLAN-02 §0.2), which makes it tempting to skip the challenge entirely -- but then
  the seam a real OTP provider drops into doesn't exist, and "add real auth later" becomes
  a rewrite rather than one new implementation of this protocol.

**Identity is `(email, role)`, not `email`.** One person may legitimately hold both a buyer
account and a seller account on one address -- a dealer who also buys a car is not an edge
case -- and forcing a single global row would make them pick. The uniqueness constraint is
on the pair, in the database, not only in application logic.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from src.domain.identity import (
    TOKEN_TTL_HOURS,
    Account,
    AccountRole,
    AuthToken,
    BuyerProfile,
    SellerProfile,
    is_demo_otp,
)

#: How long a started login stays completable. Short enough to be a real constraint, long
#: enough that reading a code off a phone and typing it never races it.
CHALLENGE_TTL_MINUTES = 10

#: `token_urlsafe(32)` yields 43 characters -- comfortably over `AuthToken`'s 32-char floor.
TOKEN_BYTES = 32


class OtpChallengeError(Exception):
    """No live challenge for this `(email, role)`, or the code was wrong.

    Deliberately one error for both cases: "that code is wrong" and "you never asked for a
    code" are different facts, and telling an unauthenticated caller which one applies is
    how an endpoint becomes an account-enumeration oracle. The distinction is preserved in
    `reason` for logs, never in what the transport returns.
    """

    def __init__(self, reason: str) -> None:
        super().__init__("that code did not match, or the login has expired")
        self.reason = reason


@dataclass(frozen=True)
class OtpChallenge:
    email: str
    role: AccountRole
    issued_at: datetime
    expires_at: datetime

    def is_valid_at(self, now: datetime) -> bool:
        return now < self.expires_at


def normalise_email(email: str) -> str:
    """Lowercased and stripped. Done in one place so a login and a signup that differ only
    in capitalisation resolve to the same account rather than two."""
    return email.strip().lower()


def mint_token_value() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


class AccountStore(Protocol):
    async def request_otp(
        self, *, email: str, role: AccountRole, now: datetime | None = None
    ) -> OtpChallenge:
        """Starts a login. Always succeeds for a well-formed address -- it must not reveal
        whether an account exists, which is why signup and login are one flow."""
        ...

    async def verify_otp(
        self,
        *,
        email: str,
        role: AccountRole,
        code: str,
        full_name: str,
        phone: str,
        profile_fields: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> tuple[Account, AuthToken, bool]:
        """Consumes a challenge and returns `(account, token, was_created)`.

        Creates the account on first successful verification -- signup and login are the
        same gesture, which is both what the demo needs and what keeps this endpoint from
        leaking which addresses are already registered.
        """
        ...

    async def sign_in_external(
        self,
        *,
        email: str,
        role: AccountRole,
        full_name: str,
        phone: str = "",
        profile_fields: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> tuple[Account, AuthToken, bool]:
        """Sign in someone a third party (Google) has already verified.

        No OTP challenge, because there is nothing to challenge -- the provider proved
        ownership of the address before redirecting back. Everything downstream is identical
        to `verify_otp`: same `(email, role)` identity, same account row, same session token,
        so a person who signs in with Google once and by email the next time lands on the
        *same* account rather than a second one.

        `phone` may be empty: Google's `email`/`profile` scopes do not include a number, and
        demanding one before the account exists would put a form in the middle of a
        one-click flow. Checkout collects it when it is actually needed.
        """
        ...

    async def claim_dealership(self, account_id: uuid.UUID, dealer_id: uuid.UUID) -> SellerProfile:
        """Attach a dealership to a seller who has none.

        Deliberately **only** valid while `dealer_id` is `None`. Two reasons: a seller who
        signed up via Google never saw the picker and has to claim one afterwards, and an
        account created before the field was required is otherwise stuck forever on a console
        that can never fill. Allowing a *change* would be a different feature with a different
        risk -- leads already routed to the old dealership would silently move.
        """
        ...

    async def get_account(self, account_id: uuid.UUID) -> Account | None: ...

    async def find_account(self, *, email: str, role: AccountRole) -> Account | None: ...

    async def get_buyer_profile(self, account_id: uuid.UUID) -> BuyerProfile | None: ...

    async def get_seller_profile(self, account_id: uuid.UUID) -> SellerProfile | None: ...

    async def resolve_token(self, token: str, *, now: datetime | None = None) -> AuthToken | None:
        """The whole authorisation path: an opaque string in, a validated token out, `None`
        for anything unknown or expired."""
        ...

    async def revoke_token(self, token: str) -> None: ...


def build_account(
    *, email: str, role: AccountRole, full_name: str, phone: str, now: datetime
) -> Account:
    return Account(
        id=uuid.uuid4(),
        role=role,
        email=normalise_email(email),
        full_name=full_name.strip(),
        phone=phone.strip(),
        created_at=now,
    )


def build_profile(
    account: Account, profile_fields: dict[str, object] | None
) -> BuyerProfile | SellerProfile:
    """Builds the role-appropriate profile, ignoring any field the other role owns.

    `income_band` is *not* accepted here even if a caller sends it -- `BuyerProfile` derives
    it (PLAN-02 §0.3), and pydantic drops the unknown key rather than honouring it. That is
    gate 12.8 holding at the construction boundary, not just at the model.
    """
    fields = dict(profile_fields or {})
    if account.role is AccountRole.SELLER:
        return SellerProfile.model_validate({**fields, "account_id": account.id})
    return BuyerProfile.model_validate({**fields, "account_id": account.id})


class InMemoryAccountStore:
    """The whole identity schema in dicts. Used by tests, gates and `DEMO_MODE`."""

    def __init__(self) -> None:
        self._accounts: dict[uuid.UUID, Account] = {}
        self._by_identity: dict[tuple[str, AccountRole], uuid.UUID] = {}
        self._buyer_profiles: dict[uuid.UUID, BuyerProfile] = {}
        self._seller_profiles: dict[uuid.UUID, SellerProfile] = {}
        self._challenges: dict[tuple[str, AccountRole], OtpChallenge] = {}
        self._tokens: dict[str, AuthToken] = {}

    async def request_otp(
        self, *, email: str, role: AccountRole, now: datetime | None = None
    ) -> OtpChallenge:
        moment = now or datetime.now(UTC)
        challenge = OtpChallenge(
            email=normalise_email(email),
            role=role,
            issued_at=moment,
            expires_at=moment + timedelta(minutes=CHALLENGE_TTL_MINUTES),
        )
        self._challenges[(challenge.email, role)] = challenge
        return challenge

    async def verify_otp(
        self,
        *,
        email: str,
        role: AccountRole,
        code: str,
        full_name: str,
        phone: str,
        profile_fields: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> tuple[Account, AuthToken, bool]:
        moment = now or datetime.now(UTC)
        key = (normalise_email(email), role)

        challenge = self._challenges.get(key)
        if challenge is None:
            raise OtpChallengeError("no challenge was issued for this email/role")
        if not challenge.is_valid_at(moment):
            del self._challenges[key]
            raise OtpChallengeError("challenge expired")
        if not is_demo_otp(code):
            raise OtpChallengeError("code did not match")

        # Single-use: a consumed challenge cannot be replayed into a second token.
        del self._challenges[key]

        return await self._find_or_create(
            email=email,
            role=role,
            full_name=full_name,
            phone=phone,
            profile_fields=profile_fields,
            now=moment,
        )

    async def sign_in_external(
        self,
        *,
        email: str,
        role: AccountRole,
        full_name: str,
        phone: str = "",
        profile_fields: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> tuple[Account, AuthToken, bool]:
        # No challenge to consume -- Google already proved the address. Everything after that
        # is the same path `verify_otp` takes, which is what makes signing in with Google and
        # then by email land on one account rather than two.
        return await self._find_or_create(
            email=email,
            role=role,
            full_name=full_name,
            phone=phone,
            profile_fields=profile_fields,
            now=now or datetime.now(UTC),
        )

    async def _find_or_create(
        self,
        *,
        email: str,
        role: AccountRole,
        full_name: str,
        phone: str,
        profile_fields: dict[str, object] | None,
        now: datetime,
    ) -> tuple[Account, AuthToken, bool]:
        key = (normalise_email(email), role)
        account = await self.find_account(email=email, role=role)
        created = account is None
        if account is None:
            account = build_account(
                email=email, role=role, full_name=full_name, phone=phone, now=now
            )
            self._accounts[account.id] = account
            self._by_identity[key] = account.id
            profile = build_profile(account, profile_fields)
            if isinstance(profile, SellerProfile):
                self._seller_profiles[account.id] = profile
            else:
                self._buyer_profiles[account.id] = profile

        return account, await self._issue_token(account, now), created

    async def claim_dealership(self, account_id: uuid.UUID, dealer_id: uuid.UUID) -> SellerProfile:
        profile = self._seller_profiles.get(account_id)
        if profile is None:
            raise ValueError("no seller profile for that account")
        if profile.dealer_id is not None:
            # Not an update path (see the protocol docstring): moving a dealership would
            # silently re-route leads already delivered to the old one.
            raise ValueError("this account already has a dealership")
        claimed = profile.model_copy(update={"dealer_id": dealer_id})
        self._seller_profiles[account_id] = claimed
        return claimed

    async def _issue_token(self, account: Account, now: datetime) -> AuthToken:
        token = AuthToken(
            token=mint_token_value(),
            account_id=account.id,
            role=account.role,
            issued_at=now,
            expires_at=now + timedelta(hours=TOKEN_TTL_HOURS),
        )
        self._tokens[token.token] = token
        return token

    async def get_account(self, account_id: uuid.UUID) -> Account | None:
        return self._accounts.get(account_id)

    async def find_account(self, *, email: str, role: AccountRole) -> Account | None:
        account_id = self._by_identity.get((normalise_email(email), role))
        return self._accounts.get(account_id) if account_id is not None else None

    async def get_buyer_profile(self, account_id: uuid.UUID) -> BuyerProfile | None:
        return self._buyer_profiles.get(account_id)

    async def get_seller_profile(self, account_id: uuid.UUID) -> SellerProfile | None:
        return self._seller_profiles.get(account_id)

    async def resolve_token(self, token: str, *, now: datetime | None = None) -> AuthToken | None:
        found = self._tokens.get(token)
        if found is None:
            return None
        if not found.is_valid_at(now or datetime.now(UTC)):
            # Drop it on read: an expired token is never valid again, so keeping it costs
            # memory and gives a later bug something to accidentally accept.
            del self._tokens[token]
            return None
        return found

    async def revoke_token(self, token: str) -> None:
        self._tokens.pop(token, None)
