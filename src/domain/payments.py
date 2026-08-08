"""Payment contracts (PHASE-8 §5). Shapes only -- the gateway itself (mock today, a real
provider behind the same seam later, `[SCALE]`) lives in `src/adapters/payments`, mirroring
how `Quote`/`QuoteTerms` (marketplace pricing) sit in `src/domain/marketplace.py` while
`MarketplaceAdapter` (the protocol) sits in `src/adapters/protocol.py`.

CONSTITUTION IV.2 -- "card data never leaves the App iframe" -- is enforced by what is *not*
here: there is no full card number field anywhere in this module. `PaymentIntent` carries
`last4` and an `outcome_hint` the App derives from the card number **inside the sandboxed
iframe**, the same way a real client-side card element (of the kind every real-world hosted
checkout form uses) never lets the merchant's own server see a raw PAN either. See
DECISIONS.md D-036 for why this reads PHASE-8 §5's "deterministic on the card number" as
"deterministic on a card-number-derived, client-computed outcome" rather than as license to
pass the number itself across the boundary.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.money import Money


class PaymentOutcome(StrEnum):
    """The five deterministic outcomes PHASE-8 §5's test-card table names, mirrored by the
    checkout App's own client-side card->outcome table (D-036) and by
    `src/adapters/payments/mock.py`'s `CARD_OUTCOMES` (used only for tests and documentation,
    never read on the live request path -- the server never sees a card number to look up).
    """

    SUCCESS = "success"
    DECLINED_INSUFFICIENT_FUNDS = "declined_insufficient_funds"
    DECLINED_EXPIRED_CARD = "declined_expired_card"
    GATEWAY_ERROR = "gateway_error"
    TIMEOUT = "timeout"

    @property
    def is_success(self) -> bool:
        return self is PaymentOutcome.SUCCESS


#: One message per outcome, shared by the gateway (`src/adapters/payments/mock.py`) and by
#: `confirm_booking`'s response (`src/mcp/booking/tools.py`) so the two never phrase the same
#: outcome two different ways.
OUTCOME_MESSAGES: dict[PaymentOutcome, str] = {
    PaymentOutcome.SUCCESS: "Payment authorised.",
    PaymentOutcome.DECLINED_INSUFFICIENT_FUNDS: "Card declined: insufficient funds.",
    PaymentOutcome.DECLINED_EXPIRED_CARD: "Card declined: expired card.",
    PaymentOutcome.GATEWAY_ERROR: "Gateway error: the payment could not be processed.",
    PaymentOutcome.TIMEOUT: "Gateway timeout: no response was received.",
}


class PaymentIntent(BaseModel):
    """What `confirm_booking` hands the gateway. `last4` and `outcome_hint` are the *only*
    card-shaped things in it -- see this module's docstring.
    """

    model_config = ConfigDict(frozen=True)

    amount: Money
    last4: str = Field(pattern=r"^\d{4}$")
    outcome_hint: PaymentOutcome
    idempotency_key: str = Field(min_length=8)


class AuthResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: PaymentOutcome
    auth_id: str | None = Field(default=None, description="Set only when outcome is SUCCESS.")
    message: str


class CaptureResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    captured: bool
    capture_id: str | None = None


class VoidResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    voided: bool
