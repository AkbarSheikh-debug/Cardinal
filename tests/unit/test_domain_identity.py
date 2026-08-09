"""`src/domain/identity.py` -- PLAN-02 P12.

The band-boundary table and the "a crafted payload cannot set `income_band`" test are the
two that matter: the first pins a decision that two call sites would otherwise make
differently, the second is gate 12.8's actual mechanism rather than a restatement of it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.identity import (
    DEMO_OTP_CODES,
    TOKEN_TTL_HOURS,
    Account,
    AccountRole,
    AuthToken,
    BuyerProfile,
    CustomerType,
    IncomeBand,
    SellerProfile,
    band_for_income,
    is_demo_otp,
)
from src.domain.money import Money

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _account(role: AccountRole = AccountRole.BUYER) -> Account:
    return Account(
        id=uuid.uuid4(),
        role=role,
        email="buyer@example.com",
        full_name="Test Buyer",
        phone="+49 170 1234567",
        created_at=NOW,
    )


def _buyer_profile(**overrides: object) -> BuyerProfile:
    base: dict[str, object] = {
        "account_id": uuid.uuid4(),
        "city": "Berlin",
        "country": "DE",
    }
    base.update(overrides)
    return BuyerProfile.model_validate(base)


# -- income bands -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (None, IncomeBand.UNDISCLOSED),
        ("0", IncomeBand.UNDER_25K),
        ("24999.99", IncomeBand.UNDER_25K),
        # Boundaries land in the *upper* band -- decided once, here (PLAN-02 §0.3).
        ("25000", IncomeBand.FROM_25K),
        ("49999.99", IncomeBand.FROM_25K),
        ("50000", IncomeBand.FROM_50K),
        ("99999.99", IncomeBand.FROM_50K),
        ("100000", IncomeBand.OVER_100K),
        ("2500000", IncomeBand.OVER_100K),
    ],
)
def test_band_for_income_covers_every_boundary(amount: str | None, expected: IncomeBand) -> None:
    income = Money.of(amount) if amount is not None else None
    assert band_for_income(income) is expected


def test_income_band_is_derived_from_the_exact_figure() -> None:
    profile = _buyer_profile(annual_income=Money.of("62000"))
    assert profile.income_band is IncomeBand.FROM_50K
    # The exact figure is still there -- coarsening happens at the boundary, not at capture.
    assert profile.annual_income == Money.of("62000")


def test_income_band_appears_in_model_dump_so_the_scorer_can_read_it() -> None:
    dumped = _buyer_profile(annual_income=Money.of("30000")).model_dump()
    assert dumped["income_band"] == IncomeBand.FROM_25K


def test_a_crafted_payload_cannot_set_income_band_independently() -> None:
    """Gate 12.8's mechanism. `income_band` is a computed field: there is no setter and no
    validation input for it, so a request body claiming a band it hasn't earned is ignored
    rather than trusted."""
    profile = BuyerProfile.model_validate(
        {
            "account_id": uuid.uuid4(),
            "city": "Berlin",
            "country": "DE",
            "annual_income": None,
            "income_band": IncomeBand.OVER_100K.value,
        }
    )
    assert profile.income_band is IncomeBand.UNDISCLOSED
    assert profile.annual_income is None


def test_undisclosed_income_is_a_real_answer_not_an_error() -> None:
    profile = _buyer_profile()
    assert profile.annual_income is None
    assert profile.income_band is IncomeBand.UNDISCLOSED


def test_annual_income_refuses_a_float_like_every_other_money_field() -> None:
    with pytest.raises(ValidationError):
        _buyer_profile(annual_income=62000.01)


# -- accounts -----------------------------------------------------------------------


def test_account_accepts_an_ordinary_address_and_number() -> None:
    account = _account()
    assert account.role is AccountRole.BUYER
    assert account.email == "buyer@example.com"


@pytest.mark.parametrize("email", ["no-at-sign", "no@dot", "two@@ats.com", "spaces in@mail.com"])
def test_account_rejects_a_malformed_email(email: str) -> None:
    with pytest.raises(ValidationError):
        Account(
            id=uuid.uuid4(),
            role=AccountRole.BUYER,
            email=email,
            full_name="Test",
            phone="+49 170 1234567",
            created_at=NOW,
        )


def test_an_empty_phone_means_not_provided_and_is_allowed() -> None:
    """Google's `email`/`profile` scopes carry no phone number, so an account created by
    "Continue with Google" genuinely has none. Demanding one there would put a form in the
    middle of a one-click flow; checkout collects it at the point it is needed. "" is
    *absent*, and still distinguishable from a malformed one (below)."""
    account = Account(
        id=uuid.uuid4(),
        role=AccountRole.BUYER,
        email="google-user@example.com",
        full_name="Google User",
        phone="",
        created_at=NOW,
    )
    assert account.phone == ""


@pytest.mark.parametrize("phone", ["abc", "12345", "+" + "9" * 25])
def test_account_rejects_a_malformed_phone(phone: str) -> None:
    with pytest.raises(ValidationError):
        Account(
            id=uuid.uuid4(),
            role=AccountRole.BUYER,
            email="a@b.co",
            full_name="Test",
            phone=phone,
            created_at=NOW,
        )


def test_seller_profile_has_no_dealer_until_p13_creates_one() -> None:
    seller = SellerProfile(account_id=uuid.uuid4())
    assert seller.dealer_id is None
    assert seller.role_title == "Sales"


def test_customer_type_defaults_to_individual() -> None:
    assert _buyer_profile().customer_type is CustomerType.INDIVIDUAL


# -- demo OTP -----------------------------------------------------------------------


def test_the_three_documented_demo_codes_are_exactly_these() -> None:
    """These three are quoted in the README and the plan doc; a silent change breaks a
    documented demo, so pin them rather than trusting the constant to stay put."""
    assert DEMO_OTP_CODES == ("123456", "234567", "345678")


@pytest.mark.parametrize("code", DEMO_OTP_CODES)
def test_every_demo_code_authenticates(code: str) -> None:
    assert is_demo_otp(code)


@pytest.mark.parametrize("code", ["000000", "12345", "1234567", "", "abcdef", "123 456"])
def test_a_code_that_is_not_one_of_the_three_is_rejected(code: str) -> None:
    assert not is_demo_otp(code)


def test_surrounding_whitespace_is_forgiven() -> None:
    """Pasted from a chat message, a code arrives with whitespace far more often than not."""
    assert is_demo_otp("  123456 \n")


# -- tokens -------------------------------------------------------------------------


def _token(expires_in: timedelta) -> AuthToken:
    return AuthToken(
        token="t" * 32,
        account_id=uuid.uuid4(),
        role=AccountRole.BUYER,
        issued_at=NOW,
        expires_at=NOW + expires_in,
    )


def test_a_fresh_token_is_valid() -> None:
    assert _token(timedelta(hours=TOKEN_TTL_HOURS)).is_valid_at(NOW)


def test_a_token_is_invalid_at_and_after_its_expiry() -> None:
    token = _token(timedelta(hours=1))
    assert not token.is_valid_at(NOW + timedelta(hours=1))
    assert not token.is_valid_at(NOW + timedelta(hours=2))


def test_a_short_token_is_refused_at_construction() -> None:
    with pytest.raises(ValidationError):
        AuthToken(
            token="tooshort",
            account_id=uuid.uuid4(),
            role=AccountRole.BUYER,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
