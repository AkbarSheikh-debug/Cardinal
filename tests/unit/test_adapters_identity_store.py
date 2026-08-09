"""`src/adapters/identity_store.py` -- PLAN-02 P12.

The behaviours worth pinning are the flow properties, not the storage: a challenge is
single-use, `(email, role)` is the identity, and a crafted `income_band` is dropped at the
construction boundary rather than trusted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.adapters.identity_store import (
    CHALLENGE_TTL_MINUTES,
    InMemoryAccountStore,
    OtpChallengeError,
    build_account,
    build_profile,
    normalise_email,
)
from src.domain.identity import (
    TOKEN_TTL_HOURS,
    AccountRole,
    BuyerProfile,
    IncomeBand,
    SellerProfile,
)
from src.domain.money import Money

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


async def _login(
    store: InMemoryAccountStore,
    *,
    email: str = "buyer@example.com",
    role: AccountRole = AccountRole.BUYER,
    code: str = "123456",
    full_name: str = "Test Buyer",
    phone: str = "+49 170 1234567",
    profile_fields: dict[str, object] | None = None,
    now: datetime = NOW,
):
    await store.request_otp(email=email, role=role, now=now)
    return await store.verify_otp(
        email=email,
        role=role,
        code=code,
        full_name=full_name,
        phone=phone,
        profile_fields=profile_fields or {"city": "Berlin", "country": "DE"},
        now=now,
    )


# -- the happy path -----------------------------------------------------------------


async def test_a_first_login_creates_the_account_and_issues_a_token() -> None:
    store = InMemoryAccountStore()
    account, token, created = await _login(store)

    assert created
    assert account.role is AccountRole.BUYER
    assert token.account_id == account.id
    assert token.expires_at == NOW + timedelta(hours=TOKEN_TTL_HOURS)


async def test_a_second_login_reuses_the_account() -> None:
    store = InMemoryAccountStore()
    first, first_token, created_first = await _login(store)
    second, second_token, created_second = await _login(store)

    assert created_first and not created_second
    assert first.id == second.id
    # A fresh token each time -- logging in twice must not resurrect the earlier session's
    # string, or revoking one would silently revoke the other.
    assert first_token.token != second_token.token


@pytest.mark.parametrize("code", ["123456", "234567", "345678"])
async def test_every_demo_code_completes_a_login(code: str) -> None:
    store = InMemoryAccountStore()
    _, token, _ = await _login(store, code=code)
    assert await store.resolve_token(token.token, now=NOW) is not None


# -- the challenge is a real gate ---------------------------------------------------


async def test_verify_without_request_is_refused() -> None:
    store = InMemoryAccountStore()
    with pytest.raises(OtpChallengeError):
        await store.verify_otp(
            email="nobody@example.com",
            role=AccountRole.BUYER,
            code="123456",
            full_name="X",
            phone="+49 170 1234567",
            now=NOW,
        )


async def test_a_wrong_code_is_refused() -> None:
    store = InMemoryAccountStore()
    with pytest.raises(OtpChallengeError):
        await _login(store, code="999999")


async def test_a_challenge_is_single_use() -> None:
    """A double-submitted login form must not mint two tokens off one challenge."""
    store = InMemoryAccountStore()
    await store.request_otp(email="buyer@example.com", role=AccountRole.BUYER, now=NOW)
    await store.verify_otp(
        email="buyer@example.com",
        role=AccountRole.BUYER,
        code="123456",
        full_name="Test Buyer",
        phone="+49 170 1234567",
        profile_fields={"city": "Berlin", "country": "DE"},
        now=NOW,
    )
    with pytest.raises(OtpChallengeError):
        await store.verify_otp(
            email="buyer@example.com",
            role=AccountRole.BUYER,
            code="123456",
            full_name="Test Buyer",
            phone="+49 170 1234567",
            now=NOW,
        )


async def test_an_expired_challenge_is_refused() -> None:
    store = InMemoryAccountStore()
    await store.request_otp(email="buyer@example.com", role=AccountRole.BUYER, now=NOW)
    later = NOW + timedelta(minutes=CHALLENGE_TTL_MINUTES + 1)
    with pytest.raises(OtpChallengeError):
        await store.verify_otp(
            email="buyer@example.com",
            role=AccountRole.BUYER,
            code="123456",
            full_name="Test Buyer",
            phone="+49 170 1234567",
            now=later,
        )


async def test_the_error_message_does_not_say_which_half_failed() -> None:
    """An unauthenticated caller must not learn whether an address is registered."""
    no_challenge = OtpChallengeError("no challenge was issued for this email/role")
    wrong_code = OtpChallengeError("code did not match")
    assert str(no_challenge) == str(wrong_code)
    # The distinction survives for logs, just not for the caller.
    assert no_challenge.reason != wrong_code.reason


# -- identity is (email, role) ------------------------------------------------------


async def test_one_address_can_hold_a_buyer_and_a_seller_account() -> None:
    store = InMemoryAccountStore()
    buyer, _, _ = await _login(store, email="both@example.com", role=AccountRole.BUYER)
    seller, _, _ = await _login(
        store, email="both@example.com", role=AccountRole.SELLER, profile_fields={}
    )
    assert buyer.id != seller.id
    assert buyer.role is AccountRole.BUYER
    assert seller.role is AccountRole.SELLER


async def test_email_case_and_whitespace_resolve_to_one_account() -> None:
    store = InMemoryAccountStore()
    first, _, _ = await _login(store, email="Buyer@Example.COM")
    second, _, created = await _login(store, email="  buyer@example.com  ")
    assert first.id == second.id
    assert not created


def test_normalise_email_lowercases_and_strips() -> None:
    assert normalise_email("  Mixed@Case.Com \n") == "mixed@case.com"


# -- profiles -----------------------------------------------------------------------


async def test_a_buyer_profile_keeps_the_exact_income_and_derives_the_band() -> None:
    store = InMemoryAccountStore()
    account, _, _ = await _login(
        store,
        profile_fields={
            "city": "Berlin",
            "country": "DE",
            "customer_type": "corporate",
            "employer": "Acme GmbH",
            "annual_income": {"amount": "72000", "currency": "EUR"},
        },
    )
    profile = await store.get_buyer_profile(account.id)
    assert profile is not None
    assert profile.annual_income == Money.of("72000")
    assert profile.income_band is IncomeBand.FROM_50K
    assert profile.employer == "Acme GmbH"


async def test_a_seller_login_stores_a_seller_profile_and_no_buyer_profile() -> None:
    store = InMemoryAccountStore()
    account, _, _ = await _login(store, role=AccountRole.SELLER, profile_fields={})
    assert await store.get_seller_profile(account.id) is not None
    assert await store.get_buyer_profile(account.id) is None


def test_build_profile_drops_a_crafted_income_band() -> None:
    """Gate 12.8 at the construction boundary, not just on the model."""
    account = build_account(
        email="b@example.com",
        role=AccountRole.BUYER,
        full_name="B",
        phone="+49 170 1234567",
        now=NOW,
    )
    profile = build_profile(
        account,
        {
            "city": "Berlin",
            "country": "DE",
            "annual_income": None,
            "income_band": IncomeBand.OVER_100K.value,
        },
    )
    assert isinstance(profile, BuyerProfile)
    assert profile.income_band is IncomeBand.UNDISCLOSED


def test_build_profile_routes_on_role() -> None:
    seller = build_account(
        email="s@example.com",
        role=AccountRole.SELLER,
        full_name="S",
        phone="+49 170 1234567",
        now=NOW,
    )
    assert isinstance(build_profile(seller, {}), SellerProfile)


# -- tokens -------------------------------------------------------------------------


async def test_an_expired_token_stops_resolving() -> None:
    store = InMemoryAccountStore()
    _, token, _ = await _login(store)
    later = NOW + timedelta(hours=TOKEN_TTL_HOURS + 1)
    assert await store.resolve_token(token.token, now=later) is None


async def test_a_revoked_token_stops_resolving() -> None:
    store = InMemoryAccountStore()
    _, token, _ = await _login(store)
    await store.revoke_token(token.token)
    assert await store.resolve_token(token.token, now=NOW) is None


async def test_an_unknown_token_resolves_to_none() -> None:
    store = InMemoryAccountStore()
    assert await store.resolve_token("not-a-real-token", now=NOW) is None


async def test_tokens_are_not_guessable_from_each_other() -> None:
    store = InMemoryAccountStore()
    tokens = set()
    for index in range(20):
        _, token, _ = await _login(store, email=f"buyer{index}@example.com")
        tokens.add(token.token)
    assert len(tokens) == 20


async def test_get_account_returns_none_for_an_unknown_id() -> None:
    store = InMemoryAccountStore()
    assert await store.get_account(uuid.uuid4()) is None
