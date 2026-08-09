"""The seller behind a listing (PLAN-02 P13, proposal doc #4).

`Listing.source` is an adapter name -- `"mock_autobazaar"` -- which identifies which
*integration* fetched a row, not which *business* is selling the car. A buyer cannot picture,
call, or drive to an adapter name, and a payment cannot be disclosed as going to one.

This module adds the entity three later features all hang off:

- **P14's payee disclosure.** `PayeeIdentity` is the projection the checkout App renders
  before the pay button. It exists here, next to `Dealer`, rather than in the API layer,
  because "who is receiving this money" is a domain fact, not a serialisation detail.
- **P15's lead routing.** A lead is routed to the dealer that owns the listing.
- **`SellerProfile.dealer_id`** (P12) finally has something real to point at.

Pure: no clock, no database, no network (CONSTITUTION II.1).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

#: Stable namespace, so `dealer_uuid` is reproducible across processes and across seed runs
#: -- gate 13.2 compares two generator runs byte for byte, exactly as gate 1.6 does for the
#: catalogue. A different namespace from `LISTING_NAMESPACE` so a dealer ref and a listing
#: ref that happen to share a string can never collide on a primary key.
DEALER_NAMESPACE = uuid.UUID("2f5b7a10-9c34-4c7e-8f21-6d0a3b1e4c88")


def dealer_uuid(source: str, dealer_ref: str) -> uuid.UUID:
    """Derive a dealer's primary key from its natural key, mirroring `listing_uuid`."""
    return uuid.uuid5(DEALER_NAMESPACE, f"{source}:{dealer_ref}")


class VerificationStatus(StrEnum):
    """Whether this business has been checked, and honest when it hasn't.

    `UNVERIFIED` is a first-class value that the checkout UI renders as a visible flag
    (PLAN-02 P14, gate 14.5). There is deliberately no "unknown" or `None`: a payee whose
    status nobody established is exactly what `UNVERIFIED` means, and giving that state two
    spellings is how one of them ends up rendering as blank.
    """

    VERIFIED = "verified"
    PENDING = "pending"
    UNVERIFIED = "unverified"


class Dealer(BaseModel):
    """A business that lists vehicles on a marketplace.

    `legal_name` and `display_name` are separate on purpose, and the distinction is the whole
    point of the entity for P14: a buyer recognises the forecourt's trading name, but the
    money goes to the registered legal entity, and a checkout that shows only the friendly
    one is hiding the fact that matters.
    """

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    #: Which marketplace adapter carries this dealer's listings.
    source: str = Field(min_length=1)
    #: The marketplace's own identifier, e.g. `"AB-D014"`. Natural key with `source`.
    dealer_ref: str = Field(min_length=1)

    legal_name: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=120)

    address: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=64)
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    phone: str = Field(min_length=6, max_length=32)

    rating: Decimal = Field(ge=Decimal("0.0"), le=Decimal("5.0"), decimal_places=1)
    review_count: int = Field(ge=0)
    verification_status: VerificationStatus
    marketplace_profile_url: str = Field(min_length=1, max_length=300)

    @property
    def natural_key(self) -> tuple[str, str]:
        return (self.source, self.dealer_ref)

    @property
    def is_verified(self) -> bool:
        return self.verification_status is VerificationStatus.VERIFIED


class PayeeIdentity(BaseModel):
    """What the buyer is shown before money moves (PLAN-02 §0.1, proposal doc #8).

    A *view model*, not a second source of truth -- every field is copied straight from a
    `Dealer` with no recomputation, the same discipline D-026 established for rendering P5's
    `ScoreBreakdown`. It exists as its own type so that the checkout surface cannot
    accidentally be handed a whole `Dealer` and start rendering fields nobody reviewed for
    that context.
    """

    model_config = ConfigDict(frozen=True)

    legal_name: str
    display_name: str
    address: str
    city: str
    country: str
    phone: str
    verification_status: VerificationStatus

    @classmethod
    def of(cls, dealer: Dealer) -> Self:
        return cls(
            legal_name=dealer.legal_name,
            display_name=dealer.display_name,
            address=dealer.address,
            city=dealer.city,
            country=dealer.country,
            phone=dealer.phone,
            verification_status=dealer.verification_status,
        )

    @property
    def is_verified(self) -> bool:
        return self.verification_status is VerificationStatus.VERIFIED

    @property
    def needs_flag(self) -> bool:
        """True whenever the UI must show a visible caution rather than stay silent.

        Anything that is not positively `VERIFIED` earns the flag -- `PENDING` included.
        "We haven't finished checking" is information a buyer about to send money is
        entitled to, and collapsing it into the verified case is the exact silence
        PLAN-02 P14's gate 14.5 exists to forbid.
        """
        return not self.is_verified

    @property
    def one_line(self) -> str:
        """`legal_name — address, city` for a single-line disclosure. Never the phone: a
        phone number belongs on its own line where it can be tapped, not buried in prose."""
        return f"{self.legal_name} — {self.address}, {self.city}"
