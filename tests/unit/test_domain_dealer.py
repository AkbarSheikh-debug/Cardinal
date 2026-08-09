"""`src/domain/dealer.py` and the `condition` enum -- PLAN-02 P13.

The two that matter: `PayeeIdentity.needs_flag` treats *anything but verified* as needing a
visible caution (P14 renders it, gate 13.7 asserts it), and `dealer_uuid` is stable across
processes so a re-seed does not orphan every listing.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.dealer import (
    DEALER_NAMESPACE,
    Dealer,
    PayeeIdentity,
    VerificationStatus,
    dealer_uuid,
)
from src.domain.enums import VehicleCondition
from src.domain.listing import listing_uuid


def _dealer(
    status: VerificationStatus = VerificationStatus.VERIFIED, **overrides: object
) -> Dealer:
    base: dict[str, object] = {
        "id": dealer_uuid("mock_autobazaar", "AB-D001"),
        "source": "mock_autobazaar",
        "dealer_ref": "AB-D001",
        "legal_name": "Nordkap Automobile GmbH",
        "display_name": "Nordkap Automobile Berlin",
        "address": "Gewerbestrasse 14",
        "city": "Berlin",
        "country": "DE",
        "phone": "+49 30 123 4567",
        "rating": Decimal("4.3"),
        "review_count": 218,
        "verification_status": status,
        "marketplace_profile_url": "https://mock-autobazaar.example/dealers/ab-d001",
    }
    base.update(overrides)
    return Dealer.model_validate(base)


# -- identity ------------------------------------------------------------------------


def test_dealer_uuid_is_stable_for_the_same_natural_key() -> None:
    assert dealer_uuid("mock_autobazaar", "AB-D001") == dealer_uuid("mock_autobazaar", "AB-D001")


def test_dealer_uuid_differs_by_source_and_by_ref() -> None:
    assert dealer_uuid("a", "X-1") != dealer_uuid("b", "X-1")
    assert dealer_uuid("a", "X-1") != dealer_uuid("a", "X-2")


def test_a_dealer_ref_and_a_listing_ref_never_collide() -> None:
    """Different namespaces, so a dealer and a listing that share a string cannot share a
    primary key -- the kind of collision that would show up as a baffling foreign-key error."""
    assert dealer_uuid("s", "X-1") != listing_uuid("s", "X-1")
    assert DEALER_NAMESPACE != uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def test_natural_key_is_source_and_ref() -> None:
    assert _dealer().natural_key == ("mock_autobazaar", "AB-D001")


# -- validation ----------------------------------------------------------------------


@pytest.mark.parametrize("rating", [Decimal("-0.1"), Decimal("5.1"), Decimal("9")])
def test_a_rating_outside_zero_to_five_is_refused(rating: Decimal) -> None:
    with pytest.raises(ValidationError):
        _dealer(rating=rating)


def test_a_negative_review_count_is_refused() -> None:
    with pytest.raises(ValidationError):
        _dealer(review_count=-1)


def test_a_country_that_is_not_two_letters_is_refused() -> None:
    with pytest.raises(ValidationError):
        _dealer(country="DEU")


# -- payee disclosure (gate 13.7) ----------------------------------------------------


def test_payee_copies_every_field_without_recomputation() -> None:
    dealer = _dealer()
    payee = PayeeIdentity.of(dealer)
    assert payee.legal_name == dealer.legal_name
    assert payee.display_name == dealer.display_name
    assert payee.address == dealer.address
    assert payee.city == dealer.city
    assert payee.country == dealer.country
    assert payee.phone == dealer.phone
    assert payee.verification_status is dealer.verification_status


def test_a_verified_payee_needs_no_flag() -> None:
    payee = PayeeIdentity.of(_dealer(VerificationStatus.VERIFIED))
    assert payee.is_verified
    assert not payee.needs_flag


@pytest.mark.parametrize("status", [VerificationStatus.UNVERIFIED, VerificationStatus.PENDING])
def test_anything_short_of_verified_earns_a_visible_flag(status: VerificationStatus) -> None:
    """Gate 13.7. `PENDING` counts: "we haven't finished checking" is information a buyer
    about to send money is entitled to, and collapsing it into the verified case is the
    silence P14's disclosure exists to prevent."""
    payee = PayeeIdentity.of(_dealer(status))
    assert not payee.is_verified
    assert payee.needs_flag


def test_the_one_line_disclosure_names_the_legal_entity_not_the_trading_name() -> None:
    """The money goes to the registered entity. A checkout showing only the friendly
    forecourt name is hiding the fact that actually matters."""
    payee = PayeeIdentity.of(_dealer())
    assert payee.one_line.startswith("Nordkap Automobile GmbH")
    assert "Gewerbestrasse 14" in payee.one_line
    assert "Berlin" in payee.one_line
    # Never the phone -- it belongs on its own tappable line, not buried in prose.
    assert "+49" not in payee.one_line


# -- condition -----------------------------------------------------------------------


def test_cpo_counts_as_used_because_it_has_had_an_owner() -> None:
    assert VehicleCondition.CERTIFIED_PRE_OWNED.is_used
    assert VehicleCondition.USED.is_used
    assert not VehicleCondition.NEW.is_used


def test_new_and_cpo_carry_a_manufacturer_warranty_and_plain_used_does_not() -> None:
    assert VehicleCondition.NEW.has_manufacturer_warranty
    assert VehicleCondition.CERTIFIED_PRE_OWNED.has_manufacturer_warranty
    assert not VehicleCondition.USED.has_manufacturer_warranty


def test_cpo_is_its_own_value_not_a_flag_on_used() -> None:
    """The value a buyer actually shops for. Folding it into USED would make the
    manufacturer-backed warranty undiscoverable."""
    assert len(set(VehicleCondition)) == 3
    assert VehicleCondition.CERTIFIED_PRE_OWNED is not VehicleCondition.USED
