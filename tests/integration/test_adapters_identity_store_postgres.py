"""`PostgresAccountStore` -- PLAN-02 P12's durable path.

Every test goes through a **fresh store instance over a fresh sessionmaker** for the read
half, which is what "survives a process restart" actually means here (the same stand-in
gates 3.2/4.1 already use). An assertion that read back through the same instance would
pass against a store that never wrote anything to Postgres at all.

Skipped when `CARDINAL_DATABASE_URL` is unset, same convention as the other Postgres suites.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from src.adapters.db.identity_store import PostgresAccountStore
from src.adapters.db.session import dispose_engine, session_factory
from src.adapters.identity_store import CHALLENGE_TTL_MINUTES, OtpChallengeError
from src.domain.identity import TOKEN_TTL_HOURS, AccountRole, IncomeBand
from src.domain.money import Money

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def _cleanup_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()


def _store() -> PostgresAccountStore:
    return PostgresAccountStore(session_factory())


def _unique_email(prefix: str) -> str:
    """Each test owns its own address, so a re-run against a database that already has rows
    from the last run doesn't collide on `UNIQUE (email, role)`."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


async def _login(
    store: PostgresAccountStore,
    email: str,
    *,
    role: AccountRole = AccountRole.BUYER,
    code: str = "123456",
    profile_fields: dict[str, object] | None = None,
    now: datetime = NOW,
):
    await store.request_otp(email=email, role=role, now=now)
    return await store.verify_otp(
        email=email,
        role=role,
        code=code,
        full_name="Postgres Buyer",
        phone="+49 170 1234567",
        profile_fields=profile_fields
        if profile_fields is not None
        else {
            "city": "Berlin",
            "country": "DE",
        },
        now=now,
    )


async def test_an_account_round_trips_through_a_fresh_store_instance(
    database_url_or_skip: str,
) -> None:
    email = _unique_email("roundtrip")
    account, _, created = await _login(_store(), email)
    assert created

    resumed = await _store().find_account(email=email, role=AccountRole.BUYER)
    assert resumed is not None
    assert resumed.id == account.id
    assert resumed.full_name == "Postgres Buyer"
    assert resumed.email == email


async def test_the_exact_income_survives_and_the_band_is_still_derived(
    database_url_or_skip: str,
) -> None:
    """Gate 12.5 + 12.8 together: the figure persists, and the band is recomputed from it on
    load rather than being a stored value that could drift out of step."""
    email = _unique_email("income")
    account, _, _ = await _login(
        _store(),
        email,
        profile_fields={
            "city": "Munich",
            "country": "DE",
            "customer_type": "corporate",
            "annual_income": {"amount": "72000", "currency": "EUR"},
        },
    )

    profile = await _store().get_buyer_profile(account.id)
    assert profile is not None
    assert profile.annual_income == Money.of("72000")
    assert profile.income_band is IncomeBand.FROM_50K
    assert profile.customer_type.value == "corporate"


async def test_one_address_holds_a_buyer_and_a_seller_account(
    database_url_or_skip: str,
) -> None:
    """`UNIQUE (email, role)`, not `UNIQUE (email)` -- asserted against the real constraint."""
    email = _unique_email("both")
    buyer, _, _ = await _login(_store(), email, role=AccountRole.BUYER)
    seller, _, _ = await _login(_store(), email, role=AccountRole.SELLER, profile_fields={})

    assert buyer.id != seller.id
    assert await _store().get_buyer_profile(buyer.id) is not None
    assert await _store().get_seller_profile(seller.id) is not None
    # A buyer account has no seller profile, even sharing an address with one that does.
    assert await _store().get_seller_profile(buyer.id) is None


async def test_a_second_login_reuses_the_account_and_mints_a_new_token(
    database_url_or_skip: str,
) -> None:
    email = _unique_email("second")
    first, first_token, created_first = await _login(_store(), email)
    second, second_token, created_second = await _login(_store(), email)

    assert created_first and not created_second
    assert first.id == second.id
    assert first_token.token != second_token.token
    # Both remain valid: signing in on a second device must not sign out the first.
    assert await _store().resolve_token(first_token.token, now=NOW) is not None
    assert await _store().resolve_token(second_token.token, now=NOW) is not None


async def test_a_token_resolves_and_revokes_across_instances(
    database_url_or_skip: str,
) -> None:
    _, token, _ = await _login(_store(), _unique_email("token"))

    resolved = await _store().resolve_token(token.token, now=NOW)
    assert resolved is not None
    assert resolved.role is AccountRole.BUYER

    await _store().revoke_token(token.token)
    assert await _store().resolve_token(token.token, now=NOW) is None


async def test_an_expired_token_stops_resolving_and_is_dropped(
    database_url_or_skip: str,
) -> None:
    _, token, _ = await _login(_store(), _unique_email("expiry"))
    later = NOW + timedelta(hours=TOKEN_TTL_HOURS + 1)

    assert await _store().resolve_token(token.token, now=later) is None
    # Dropped on read, so a clock correction cannot resurrect it.
    assert await _store().resolve_token(token.token, now=NOW) is None


async def test_a_challenge_is_single_use_across_instances(
    database_url_or_skip: str,
) -> None:
    """The property that stops a double-submitted login minting two tokens -- asserted
    against the real table rather than a process-local dict."""
    email = _unique_email("single-use")
    await _store().request_otp(email=email, role=AccountRole.BUYER, now=NOW)
    await _store().verify_otp(
        email=email,
        role=AccountRole.BUYER,
        code="123456",
        full_name="Postgres Buyer",
        phone="+49 170 1234567",
        profile_fields={"city": "Berlin", "country": "DE"},
        now=NOW,
    )
    with pytest.raises(OtpChallengeError):
        await _store().verify_otp(
            email=email,
            role=AccountRole.BUYER,
            code="123456",
            full_name="Postgres Buyer",
            phone="+49 170 1234567",
            now=NOW,
        )


async def test_an_expired_challenge_is_refused(database_url_or_skip: str) -> None:
    email = _unique_email("stale")
    await _store().request_otp(email=email, role=AccountRole.BUYER, now=NOW)
    with pytest.raises(OtpChallengeError):
        await _store().verify_otp(
            email=email,
            role=AccountRole.BUYER,
            code="123456",
            full_name="Postgres Buyer",
            phone="+49 170 1234567",
            now=NOW + timedelta(minutes=CHALLENGE_TTL_MINUTES + 1),
        )


async def test_a_wrong_code_leaves_the_challenge_usable(database_url_or_skip: str) -> None:
    """A typo must not burn the login -- retrying with the right code has to work."""
    email = _unique_email("typo")
    await _store().request_otp(email=email, role=AccountRole.BUYER, now=NOW)
    with pytest.raises(OtpChallengeError):
        await _store().verify_otp(
            email=email,
            role=AccountRole.BUYER,
            code="999999",
            full_name="Postgres Buyer",
            phone="+49 170 1234567",
            now=NOW,
        )
    account, token, created = await _store().verify_otp(
        email=email,
        role=AccountRole.BUYER,
        code="234567",
        full_name="Postgres Buyer",
        phone="+49 170 1234567",
        profile_fields={"city": "Berlin", "country": "DE"},
        now=NOW,
    )
    assert created and token.account_id == account.id
