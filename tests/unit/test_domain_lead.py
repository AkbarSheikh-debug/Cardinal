"""`src/domain/lead.py` -- PLAN-02 P15.

Pure pydantic. The properties worth pinning down are the ones that would otherwise be
enforced by whichever route happened to build a `Lead`: the id is derived so "one lead per
buyer per car" cannot be violated, events are a set rather than a tally so a double click
cannot inflate a tier, and every tier reads as an estimate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.lead import (
    SLA_WINDOWS,
    IntentTier,
    Lead,
    LeadEvent,
    LeadScore,
    LeadSignal,
    LeadState,
    lead_uuid,
    sla_deadline,
)

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
BUYER = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEALER = uuid.UUID("22222222-2222-2222-2222-222222222222")
LISTING = uuid.UUID("33333333-3333-3333-3333-333333333333")


def signal(name: str = "added_to_cart", value: float = 1.0, weight: float = 0.5) -> LeadSignal:
    return LeadSignal(
        name=name,
        value=value,
        weight=weight,
        contribution=weight * value,
        explanation="added this car to their cart",
    )


def score(
    tier: IntentTier = IntentTier.LOW, signals: tuple[LeadSignal, ...] | None = None
) -> LeadScore:
    parts = signals if signals is not None else (signal(weight=0.2),)
    return LeadScore(
        tier=tier,
        score=sum(s.contribution for s in parts),
        signals=parts,
        explanation=f"{tier.label} — added this car to their cart.",
    )


def lead(**overrides: object) -> Lead:
    fields: dict[str, object] = {
        "id": lead_uuid(BUYER, LISTING),
        "buyer_account_id": BUYER,
        "dealer_id": DEALER,
        "listing_id": LISTING,
        "source": "mock_autobazaar",
        "source_id": "AB-1073",
        "requirement_summary": "Buying · suv · budget EUR 30,000",
        "events": (LeadEvent.CART_ADD,),
        "score": score(),
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return Lead.model_validate(fields)


# -- identity -----------------------------------------------------------------------


def test_the_id_is_derived_from_the_buyer_and_the_car() -> None:
    """One lead per buyer per car (gate 15.1) is a property of the id, so a second insert
    collides rather than quietly becoming a duplicate somebody reconciles by hand."""
    assert lead_uuid(BUYER, LISTING) == lead_uuid(BUYER, LISTING)


def test_two_cars_from_the_same_buyer_are_two_leads() -> None:
    other = uuid.UUID("44444444-4444-4444-4444-444444444444")
    assert lead_uuid(BUYER, LISTING) != lead_uuid(BUYER, other)


def test_two_buyers_on_the_same_car_are_two_leads() -> None:
    other = uuid.UUID("55555555-5555-5555-5555-555555555555")
    assert lead_uuid(BUYER, LISTING) != lead_uuid(other, LISTING)


# -- events -------------------------------------------------------------------------


def test_a_lead_cannot_exist_with_no_events() -> None:
    """Browsing produces nothing. There is no constructor for "someone looked at your car",
    which is what makes gate 15.6 hold by construction rather than by a filter."""
    with pytest.raises(ValidationError):
        lead(events=())


def test_events_must_be_unique() -> None:
    """A lead records *which* actions happened, not how many times -- otherwise a double
    click looks like twice the intent."""
    with pytest.raises(ValidationError):
        lead(events=(LeadEvent.CART_ADD, LeadEvent.CART_ADD))


def test_recording_a_new_event_appends_and_rescores() -> None:
    hotter = score(IntentTier.HIGH, (signal(weight=0.7),))
    updated = lead().with_event(
        LeadEvent.CHECKOUT_OPENED, score=hotter, now=NOW + timedelta(hours=1)
    )

    assert updated.events == (LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED)
    assert updated.score.tier is IntentTier.HIGH
    assert updated.updated_at == NOW + timedelta(hours=1)


def test_a_repeated_event_with_an_unchanged_score_is_a_no_op() -> None:
    """No spurious `updated_at` bump: the console sorts on recency, and a re-click that
    reordered the board would make the list jump for no reason a dealer can see."""
    original = lead()
    assert (
        original.with_event(LeadEvent.CART_ADD, score=original.score, now=NOW + timedelta(hours=1))
        is original
    )


def test_a_repeated_event_with_a_changed_score_still_updates() -> None:
    """The same action a week later scores differently -- the target date got closer."""
    original = lead()
    hotter = score(IntentTier.MEDIUM, (signal(weight=0.4),))
    updated = original.with_event(LeadEvent.CART_ADD, score=hotter, now=NOW + timedelta(days=7))
    assert updated is not original
    assert updated.events == (LeadEvent.CART_ADD,)


# -- state --------------------------------------------------------------------------


def test_marking_contacted_moves_the_state_and_the_clock() -> None:
    updated = lead().with_state(LeadState.CONTACTED, now=NOW + timedelta(minutes=5))
    assert updated.state is LeadState.CONTACTED
    assert updated.updated_at == NOW + timedelta(minutes=5)


def test_setting_the_state_it_already_has_is_a_no_op() -> None:
    original = lead()
    assert original.with_state(LeadState.NEW, now=NOW + timedelta(hours=2)) is original


# -- SLA ----------------------------------------------------------------------------


def test_high_and_medium_have_deadlines_and_low_does_not() -> None:
    """Inventing a deadline for a buyer three months out would manufacture urgency the
    signals do not support, and a countdown nobody believes trains people to ignore the ones
    that matter."""
    assert SLA_WINDOWS[IntentTier.HIGH] < SLA_WINDOWS[IntentTier.MEDIUM]  # type: ignore[operator]
    assert SLA_WINDOWS[IntentTier.LOW] is None
    assert sla_deadline(IntentTier.LOW, NOW) is None
    assert sla_deadline(IntentTier.HIGH, NOW) == NOW + timedelta(hours=2)


def test_a_new_high_lead_goes_overdue_after_its_window() -> None:
    hot = lead(score=score(IntentTier.HIGH))
    assert not hot.is_overdue(NOW + timedelta(hours=1))
    assert hot.is_overdue(NOW + timedelta(hours=3))


def test_a_contacted_lead_is_never_overdue() -> None:
    """The clock measures "nobody has called yet", not "time has passed"."""
    hot = lead(score=score(IntentTier.HIGH)).with_state(LeadState.CONTACTED, now=NOW)
    assert not hot.is_overdue(NOW + timedelta(days=3))


def test_a_low_lead_is_never_overdue() -> None:
    assert not lead().is_overdue(NOW + timedelta(days=365))


# -- the score's own guarantees -----------------------------------------------------


def test_the_score_must_equal_the_sum_of_its_signals() -> None:
    """The same check `ScoreBreakdown` enforces, and what makes the "why this tier" panel
    honest: there is no hidden term, so the rows on screen *are* the score."""
    with pytest.raises(ValidationError):
        LeadScore(
            tier=IntentTier.HIGH,
            score=0.9,
            signals=(signal(weight=0.2),),
            explanation="wrong on purpose",
        )


def test_a_signal_contribution_must_be_weight_times_value() -> None:
    with pytest.raises(ValidationError):
        LeadSignal(
            name="added_to_cart", value=1.0, weight=0.5, contribution=0.9, explanation="nope"
        )


def test_ranked_signals_put_the_biggest_contributor_first() -> None:
    small, big = signal("budget_fit", 0.5, 0.1), signal("opened_checkout", 1.0, 0.4)
    ordered = score(IntentTier.MEDIUM, (small, big)).ranked_signals
    assert [s.name for s in ordered] == ["opened_checkout", "budget_fit"]


def test_ranked_signals_break_ties_deterministically() -> None:
    a, b = signal("added_to_cart", 1.0, 0.2), signal("opened_checkout", 1.0, 0.2)
    assert [s.name for s in score(IntentTier.LOW, (b, a)).ranked_signals] == [
        "added_to_cart",
        "opened_checkout",
    ]


# -- phrasing (gate 15.8) -----------------------------------------------------------


def test_every_tier_label_is_an_estimate_not_an_assertion() -> None:
    for tier in IntentTier:
        assert tier.label.endswith("(estimated)")
        assert "will buy" not in tier.label.lower()


def test_every_tier_carries_dealer_guidance() -> None:
    for tier in IntentTier:
        assert tier.guidance.strip()
