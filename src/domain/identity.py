"""Accounts, roles, and the profile fields collected at signup (PLAN-02 P12).

Two rules from `plans/PLAN-02-MARKETPLACE.md` are enforced *here*, in the types, rather than
by every caller remembering them:

- **§0.2 — demo auth is loudly demo.** `DEMO_OTP_CODES` is a module constant, not
  configuration, for exactly the reason `MOCK_GATEWAY_BASE_URL` is (CONSTITUTION I.1): no
  environment variable can turn a demo login into a claim of real authentication. There is
  no password, no hash, and no signing secret anywhere in this module -- a token is minted
  in the adapter layer and validated here against a caller-supplied `now`.

- **§0.3 — income is captured exactly and travels as a band.** `annual_income` holds the
  precise figure; `income_band` is a `computed_field` derived from it, so there is no
  setter, no route, and no `model_validate` payload that can make the two disagree. That is
  gate 12.8 satisfied by construction rather than by a check that has to be remembered.

Pure: no clock, no database, no network (CONSTITUTION II.1). Anything time-dependent takes
`now` as an argument, the same shape `src/domain/booking.py`'s `stale_pending` already uses.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.domain.money import Money

#: The three demo login codes (PLAN-02 §0.2). Any of them authenticates any account.
#: A constant, never configuration -- see this module's docstring.
DEMO_OTP_CODES: Final[tuple[str, str, str]] = ("123456", "234567", "345678")

#: Rendered unconditionally and above the fold on the login screen (CONSTITUTION I.5 applied
#: to auth exactly as it applies to payment). Gate 12.2 asserts it from a browser.
DEMO_AUTH_BANNER: Final[str] = "DEMO AUTH — ANY CODE BELOW WORKS, NOT REAL SECURITY"

#: How long a minted session token stays valid. Not a security boundary in a demo build --
#: it exists so the expiry *path* is real code with a real test, the same reasoning
#: PHASE-8 §3 gives for building the booking lifecycle around a mocked gateway.
TOKEN_TTL_HOURS: Final[int] = 24

#: Deliberately permissive. A strict RFC 5322 matcher rejects addresses that work and
#: accepts ones that don't; this catches typos ("no @", "no dot in the domain") without
#: pulling in an `email-validator` dependency for a demo signup form.
EMAIL_PATTERN: Final[str] = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

#: Digits, spaces, dashes, parens and an optional leading `+`. Formatting varies by country
#: far more than validation is worth here; the seller needs a number they can dial, not a
#: canonical E.164 string.
#:
#: The empty alternative is deliberate: Google's `email`/`profile` scopes carry no phone
#: number, so an account created by "Continue with Google" genuinely has none yet. Demanding
#: one there would put a form in the middle of a one-click flow; checkout collects it at the
#: point it is actually needed. "" means *not provided*, and is distinguishable from a bad one.
PHONE_PATTERN: Final[str] = r"^$|^\+?[0-9 ()\-]{6,20}$"


class AccountRole(StrEnum):
    """Which side of the marketplace an account acts on.

    A single account is one or the other, never both. Two roles on one login means every
    downstream authorisation check has to ask "acting as what?", and that question gets
    answered wrongly exactly once before someone sees another dealer's leads.
    """

    BUYER = "buyer"
    SELLER = "seller"


class CustomerType(StrEnum):
    """Fleet buyers and individuals follow different journeys (proposal doc #6)."""

    INDIVIDUAL = "individual"
    CORPORATE = "corporate"


class IncomeBand(StrEnum):
    """The coarsened form of `BuyerProfile.annual_income` -- the only form that travels.

    `UNDISCLOSED` is a first-class answer, not a missing one: P15's lead scorer must treat
    it as neutral rather than negative (PLAN-02 §0.3), or the field quietly starts
    penalising privacy.
    """

    UNDISCLOSED = "undisclosed"
    UNDER_25K = "under_25k"
    FROM_25K = "25k_50k"
    FROM_50K = "50k_100k"
    OVER_100K = "100k_plus"


#: Band boundaries in whole currency units, ascending. Compared with `<` against the exact
#: amount, so 25000 lands in `FROM_25K` rather than `UNDER_25K` -- a boundary that has to be
#: decided once, in one place, or two call sites will decide it differently.
_BAND_CEILINGS: Final[tuple[tuple[Decimal, IncomeBand], ...]] = (
    (Decimal(25_000), IncomeBand.UNDER_25K),
    (Decimal(50_000), IncomeBand.FROM_25K),
    (Decimal(100_000), IncomeBand.FROM_50K),
)


def band_for_income(income: Money | None) -> IncomeBand:
    """The band an exact figure falls into. Pure, total, and the only way a band is produced.

    `None` -- the buyer declined, or never answered -- is `UNDISCLOSED`, which is why the
    scorer can treat "withheld" and "not asked" identically without a second sentinel.
    """
    if income is None:
        return IncomeBand.UNDISCLOSED
    for ceiling, band in _BAND_CEILINGS:
        if income.amount < ceiling:
            return band
    return IncomeBand.OVER_100K


class Account(BaseModel):
    """Who someone is. Contact details and role -- nothing role-specific lives here."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    role: AccountRole
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(pattern=PHONE_PATTERN)
    created_at: datetime


class BuyerProfile(BaseModel):
    """The buyer-side fields collected at signup (PLAN-02 P12, proposal doc #3/#6)."""

    model_config = ConfigDict(frozen=True)

    account_id: uuid.UUID
    customer_type: CustomerType = CustomerType.INDIVIDUAL

    #: Free text, and therefore **untrusted input** -- display-only, never an input to a
    #: computed score, the same discipline `Listing.description` gets under CONSTITUTION I.4.
    employer: str | None = Field(default=None, max_length=120)

    #: The exact figure (PLAN-02 §0.3). Never leaves the buyer's own account: not to a
    #: seller (P15's privacy rule), not into a model prompt, and redacted before any span
    #: export (CONSTITUTION IV.1). `income_band` below is what travels instead.
    annual_income: Money | None = None

    #: `None` means **not stated**, which is a state Google sign-in can genuinely produce:
    #: the `email`/`profile` scopes carry no address, and no further scope would supply one.
    #:
    #: `None` rather than `""`, and `min_length` kept, so the two cases stay distinguishable
    #: -- an empty string is still refused, which is what stops the signup form (where both
    #: are `required`) from quietly writing a blank. The alternative was to have the callback
    #: invent a default city and country, which would put a fact in the profile that nobody
    #: ever told us; a field that admits it does not know is worth more than one that lies.
    city: str | None = Field(default=None, min_length=1, max_length=64)
    country: str | None = Field(
        default=None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def income_band(self) -> IncomeBand:
        """Derived, never stored, never settable.

        A `computed_field` appears in `model_dump()` (so the API and the lead scorer can
        read it) while having no setter and no place in `model_validate`'s input -- which is
        precisely why gate 12.8 cannot be made to fail by a crafted request body.
        """
        return band_for_income(self.annual_income)


class SellerProfile(BaseModel):
    """The seller-side counterpart. `dealer_id` stays `None` until P13 creates dealers."""

    model_config = ConfigDict(frozen=True)

    account_id: uuid.UUID
    #: Populated by P13 (DEALER). Nullable now so P12's gate can be green before P13 exists,
    #: rather than P12 inventing a placeholder dealer it would then have to migrate away.
    dealer_id: uuid.UUID | None = None
    role_title: str = Field(default="Sales", min_length=1, max_length=64)


class AuthToken(BaseModel):
    """An opaque bearer token. No JWT, no signature, no secret (PLAN-02 §0.2).

    Validity is a pure function of a caller-supplied `now`, so the expiry path is testable
    without freezing a clock the domain isn't allowed to read in the first place.
    """

    model_config = ConfigDict(frozen=True)

    token: str = Field(min_length=32)
    account_id: uuid.UUID
    role: AccountRole
    issued_at: datetime
    expires_at: datetime

    def is_valid_at(self, now: datetime) -> bool:
        return now < self.expires_at


def is_demo_otp(code: str) -> bool:
    """Whether `code` is one of the three demo codes.

    Compares against the whole tuple every time rather than returning early, so the check
    takes the same work regardless of which code was supplied. That is a habit worth keeping
    even where it does not matter yet -- this function is the seam a real verifier replaces.
    """
    stripped = code.strip()
    return any(stripped == valid for valid in DEMO_OTP_CODES)
