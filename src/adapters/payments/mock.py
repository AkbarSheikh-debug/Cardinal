"""The mock payment gateway (PHASE-8 §5). Mocks the network call, not the lifecycle -- see
the phase doc's own framing: "a mock that skips the hard parts teaches you nothing." Every
outcome below is a real `AuthResult` an honest gateway could return; the only thing fake is
that no bytes ever leave this process.

CONSTITUTION I.1: no payment SDK, no live gateway URL, nowhere in this repository (gate 8.7's
static denylist scan). `_BASE_URL` exists specifically so a determined future edit ("just
point this at the real staging endpoint for a demo") has nowhere to put the change -- it is a
module-level string literal, not read from `os.environ` or any settings object, so there is
no environment variable that could ever make it live.
"""

from __future__ import annotations

import uuid

from src.domain.payments import (
    OUTCOME_MESSAGES,
    AuthResult,
    CaptureResult,
    PaymentIntent,
    PaymentOutcome,
    VoidResult,
)

#: Compile-time constant, not configuration (PHASE-8 §5, CONSTITUTION I.1). `mock://` is not
#: a resolvable scheme -- nothing in this codebase ever opens a socket to it, which is the
#: point: even a caller who went looking for "the gateway URL" to repoint would find a value
#: that cannot be dialled, rather than a real hostname with an easy env-var override.
MOCK_GATEWAY_BASE_URL = "mock://cardinal-payments.internal/v1"

#: PHASE-8 §5's own table, mirrored (never re-derived) in the checkout App's client-side
#: script (`src/mcp/booking/static/checkout.html`) -- the App is the only thing that ever
#: sees a full card number (CONSTITUTION IV.2), so it is the only place this mapping is
#: actually *applied*. Kept here too, digit-string keyed, purely so `outcome_for_card_number`
#: can pin the mapping in a Python unit test and catch the two copies drifting apart -- the
#: same dual-implementation-as-the-check discipline D-034 used for CSP directives.
CARD_OUTCOMES: dict[str, PaymentOutcome] = {
    "4242424242424242": PaymentOutcome.SUCCESS,
    "4000000000000002": PaymentOutcome.DECLINED_INSUFFICIENT_FUNDS,
    "4000000000000069": PaymentOutcome.DECLINED_EXPIRED_CARD,
    "4000000000000119": PaymentOutcome.GATEWAY_ERROR,
    "4000000000000127": PaymentOutcome.TIMEOUT,
}


def outcome_for_card_number(card_number: str) -> PaymentOutcome:
    """Test/documentation-only: what the checkout App's own client-side lookup would return
    for a given number. Never called from `MockPaymentGateway` itself, and never called from
    any live request path -- the server-side gateway only ever sees the outcome the App
    already derived (`PaymentIntent.outcome_hint`), not the number that produced it.
    """
    digits = card_number.replace(" ", "")
    return CARD_OUTCOMES.get(digits, PaymentOutcome.SUCCESS)


class MockPaymentGateway:
    """Implements `PaymentGateway`. Deterministic on `intent.outcome_hint`, which by
    construction (`src/domain/payments.py`) is a card-number-derived label the App computed
    client-side, never a card number this class inspects itself.
    """

    def __init__(self) -> None:
        #: Idempotency at the gateway's own boundary too, not only at the booking store's --
        #: a real gateway would refuse to charge a second time for a repeated idempotency
        #: key even if the caller above it forgot to check first. `[MVP]`: in-memory, per
        #: process, the same posture P4/P7 used for their own first working stores.
        self._auth_by_idem: dict[str, AuthResult] = {}

    async def authorise(self, intent: PaymentIntent, idem: str) -> AuthResult:
        cached = self._auth_by_idem.get(idem)
        if cached is not None:
            return cached

        outcome = intent.outcome_hint
        auth_id = f"auth_{uuid.uuid4().hex[:20]}" if outcome.is_success else None
        result = AuthResult(outcome=outcome, auth_id=auth_id, message=OUTCOME_MESSAGES[outcome])
        self._auth_by_idem[idem] = result
        return result

    async def capture(self, auth_id: str, idem: str) -> CaptureResult:
        return CaptureResult(captured=True, capture_id=f"cap_{uuid.uuid4().hex[:20]}")

    async def void(self, auth_id: str, idem: str) -> VoidResult:
        return VoidResult(voided=True)
