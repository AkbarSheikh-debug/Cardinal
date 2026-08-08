"""The mock payment gateway (PHASE-8 §5). Every test card in the documented table produces
its documented outcome, authorisation is idempotent on its own key, and the base URL is a
compile-time constant no environment variable can override -- CONSTITUTION I.1.
"""

from __future__ import annotations

import pytest

from src.adapters.payments.mock import (
    CARD_OUTCOMES,
    MOCK_GATEWAY_BASE_URL,
    MockPaymentGateway,
    outcome_for_card_number,
)
from src.adapters.payments.protocol import PaymentGateway
from src.domain.money import Money
from src.domain.payments import PaymentIntent, PaymentOutcome


def test_mock_gateway_base_url_is_not_a_dialable_endpoint() -> None:
    """PHASE-8 §5: "the mock cannot be pointed at a real endpoint... a compile-time constant,
    not configuration." `mock://` is not a scheme anything in this codebase opens a socket
    to -- this pins the constant's value so a future edit swapping it for a real URL is a
    one-line diff someone has to consciously make, not a silent drift.
    """
    assert MOCK_GATEWAY_BASE_URL.startswith("mock://")


def test_mock_payment_gateway_satisfies_the_protocol() -> None:
    assert isinstance(MockPaymentGateway(), PaymentGateway)


@pytest.mark.parametrize(
    ("card_number", "expected"),
    [
        ("4242 4242 4242 4242", PaymentOutcome.SUCCESS),
        ("4000000000000002", PaymentOutcome.DECLINED_INSUFFICIENT_FUNDS),
        ("4000000000000069", PaymentOutcome.DECLINED_EXPIRED_CARD),
        ("4000000000000119", PaymentOutcome.GATEWAY_ERROR),
        ("4000000000000127", PaymentOutcome.TIMEOUT),
    ],
)
def test_every_documented_test_card_maps_to_its_documented_outcome(
    card_number: str, expected: PaymentOutcome
) -> None:
    assert outcome_for_card_number(card_number) == expected


def test_an_unrecognised_card_number_defaults_to_success() -> None:
    """Not one of PHASE-8 §5's five test cards -- friendliest default for a demo typing an
    arbitrary 16-digit number, not a dead end.
    """
    assert outcome_for_card_number("1111222233334444") == PaymentOutcome.SUCCESS


def test_card_outcomes_table_has_exactly_the_five_documented_entries() -> None:
    assert set(CARD_OUTCOMES) == {
        "4242424242424242",
        "4000000000000002",
        "4000000000000069",
        "4000000000000119",
        "4000000000000127",
    }


async def test_authorise_success_returns_an_auth_id() -> None:
    gateway = MockPaymentGateway()
    intent = PaymentIntent(
        amount=Money.of("20000"),
        last4="4242",
        outcome_hint=PaymentOutcome.SUCCESS,
        idempotency_key="idem-00000001",
    )
    result = await gateway.authorise(intent, idem="idem-00000001")
    assert result.outcome is PaymentOutcome.SUCCESS
    assert result.auth_id is not None


@pytest.mark.parametrize(
    "outcome",
    [
        PaymentOutcome.DECLINED_INSUFFICIENT_FUNDS,
        PaymentOutcome.DECLINED_EXPIRED_CARD,
        PaymentOutcome.GATEWAY_ERROR,
        PaymentOutcome.TIMEOUT,
    ],
)
async def test_authorise_every_non_success_outcome_carries_no_auth_id(
    outcome: PaymentOutcome,
) -> None:
    gateway = MockPaymentGateway()
    intent = PaymentIntent(
        amount=Money.of("20000"),
        last4="0002",
        outcome_hint=outcome,
        idempotency_key="idem-00000002",
    )
    result = await gateway.authorise(intent, idem="idem-00000002")
    assert result.outcome is outcome
    assert result.auth_id is None


async def test_authorise_is_idempotent_on_its_own_key() -> None:
    gateway = MockPaymentGateway()
    intent = PaymentIntent(
        amount=Money.of("20000"),
        last4="4242",
        outcome_hint=PaymentOutcome.SUCCESS,
        idempotency_key="idem-00000003",
    )
    first = await gateway.authorise(intent, idem="idem-00000003")
    second = await gateway.authorise(intent, idem="idem-00000003")
    assert first == second


async def test_capture_and_void_report_success_for_a_real_auth() -> None:
    gateway = MockPaymentGateway()
    intent = PaymentIntent(
        amount=Money.of("20000"),
        last4="4242",
        outcome_hint=PaymentOutcome.SUCCESS,
        idempotency_key="idem-00000004",
    )
    auth = await gateway.authorise(intent, idem="idem-00000004")
    assert auth.auth_id is not None
    capture = await gateway.capture(auth.auth_id, idem="idem-00000004")
    assert capture.captured is True
    void = await gateway.void(auth.auth_id, idem="idem-00000004")
    assert void.voided is True
