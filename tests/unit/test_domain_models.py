"""Domain contract round-trips (gate 0.1) and the invariants that make the catalogue
readable to someone who knows cars.
"""

from __future__ import annotations

import uuid

import pytest

from src.adapters.catalogue.generator import generate_catalogue
from src.domain.dates import DateRange
from src.domain.enums import FuelType, OfferType
from src.domain.listing import Listing, listing_uuid
from src.domain.marketplace import Availability, AvailabilityStatus, SearchQuery
from src.domain.money import Money
from src.domain.profile import RequirementProfile, Slot
from src.domain.scoring import CriterionScore, CriterionWeight, ScoreBreakdown, WeightSet
from src.domain.tco import TcoEstimate, TcoLine, TcoLineKind, TcoPath


def test_every_generated_listing_round_trips() -> None:
    """`model_validate` -> `model_dump` -> equal, for all 240 rows."""
    for listing in generate_catalogue():
        assert Listing.model_validate(listing.model_dump(mode="json")) == listing


def test_listing_rejects_an_electric_car_with_a_timing_belt() -> None:
    """The most obvious tell that a catalogue was generated without thought."""
    electric = next(item for item in generate_catalogue() if item.fuel_type is FuelType.ELECTRIC)
    payload = electric.model_dump(mode="json")
    payload["timing_mechanism"] = "belt"
    with pytest.raises(ValueError, match="no timing belt or chain"):
        Listing.model_validate(payload)


def test_listing_rejects_offer_type_pricing_mismatch() -> None:
    """A buy listing relabelled `rent` still carries `price_buy`, and must be rejected.

    Picked by offer type rather than by index: the first row of the catalogue is already a
    rental, so mutating *it* would be a no-op and the test would assert nothing.
    """
    buyable = next(item for item in generate_catalogue() if item.offer_type is OfferType.BUY)
    payload = buyable.model_dump(mode="json")
    payload["offer_type"] = "rent"
    with pytest.raises(ValueError, match="must not carry price_buy"):
        Listing.model_validate(payload)


def test_depreciation_curve_must_not_increase() -> None:
    listing = generate_catalogue()[0]
    payload = listing.model_dump(mode="json")
    payload["depreciation_curve"] = [0.5, 0.6, 0.4, 0.3, 0.2]
    with pytest.raises(ValueError, match="non-increasing"):
        Listing.model_validate(payload)


def test_raw_must_be_present() -> None:
    listing = generate_catalogue()[0]
    payload = listing.model_dump(mode="json")
    payload["raw"] = {}
    with pytest.raises(ValueError):
        Listing.model_validate(payload)


def test_residual_value_reads_the_curve() -> None:
    listing = generate_catalogue()[0]
    year_three = listing.residual_value(3)
    assert year_three < listing.market_value
    with pytest.raises(ValueError):
        listing.residual_value(6)


# ---------------------------------------------------------------------------


def test_date_range_subtract_splits_a_window_in_two() -> None:
    whole = DateRange(start="2026-04-01", end="2026-04-30")
    blocked = DateRange(start="2026-04-10", end="2026-04-15")
    parts = whole.subtract(blocked)
    assert len(parts) == 2
    assert parts[0] == DateRange(start="2026-04-01", end="2026-04-09")
    assert parts[1] == DateRange(start="2026-04-16", end="2026-04-30")


def test_date_range_rejects_reversed_ends() -> None:
    with pytest.raises(ValueError):
        DateRange(start="2026-04-30", end="2026-04-01")


def test_availability_status_and_windows_must_agree() -> None:
    window = DateRange(start="2026-04-01", end="2026-04-30")
    with pytest.raises(ValueError):
        Availability(
            source_id="X-1",
            requested=window,
            status=AvailabilityStatus.UNAVAILABLE,
            free_windows=(window,),
        )
    with pytest.raises(ValueError):
        Availability(source_id="X-1", requested=window, status=AvailabilityStatus.PARTIAL)


# ---------------------------------------------------------------------------


def test_weights_normalise_on_construction() -> None:
    raw = WeightSet(
        weights=(
            CriterionWeight(criterion="budget_fit", weight=3.0 / 4),
            CriterionWeight(criterion="resale_strength", weight=1.0 / 4),
        )
    )
    assert pytest.approx(sum(raw.as_dict().values())) == 1.0
    assert raw.as_dict()["budget_fit"] == pytest.approx(0.75)


def test_weight_set_rejects_duplicate_criteria() -> None:
    with pytest.raises(ValueError, match="duplicate criterion"):
        WeightSet(
            weights=(
                CriterionWeight(criterion="budget_fit", weight=0.5),
                CriterionWeight(criterion="budget_fit", weight=0.5),
            )
        )


def test_score_breakdown_total_must_equal_its_parts() -> None:
    criteria = (
        CriterionScore(criterion="budget_fit", weight=0.6, normalised_value=0.5, contribution=0.30),
        CriterionScore(
            criterion="resale_strength", weight=0.4, normalised_value=0.25, contribution=0.10
        ),
    )
    assert ScoreBreakdown(criteria=criteria, total=0.40).total == 0.40
    with pytest.raises(ValueError, match="sum of contributions"):
        ScoreBreakdown(criteria=criteria, total=0.99)


def test_tco_total_must_equal_its_line_items() -> None:
    lines = (
        TcoLine(kind=TcoLineKind.PURCHASE, amount=Money.of("20000")),
        TcoLine(kind=TcoLineKind.RESALE, amount=-Money.of("12000")),
    )
    assert TcoEstimate(
        path=TcoPath.BUY, horizon_months=24, lines=lines, total=Money.of("8000")
    ).total == Money.of("8000")
    with pytest.raises(ValueError, match="does not equal the sum"):
        TcoEstimate(path=TcoPath.BUY, horizon_months=24, lines=lines, total=Money.of("9999"))


# ---------------------------------------------------------------------------


def test_locked_slot_is_not_overwritten_by_inference() -> None:
    """A stated budget must not drift because a later turn inferred something else."""
    stated = Slot[int]().fill(15_000, confidence=1.0, turn=2, locked=True)
    inferred = stated.fill(30_000, confidence=0.4, turn=5)
    assert inferred.value == 15_000


def test_profile_completeness_tracks_required_slots() -> None:
    profile = RequirementProfile()
    assert profile.completeness == 0.0
    assert set(profile.missing_slots()) == set(RequirementProfile.REQUIRED)
    profile.budget = profile.budget.fill(Money.of("20000"), confidence=0.9, turn=1)
    assert 0 < profile.completeness < 1
    assert not profile.is_complete


# ---------------------------------------------------------------------------


def test_search_query_forbids_unknown_filters() -> None:
    with pytest.raises(ValueError):
        SearchQuery(colour="red")  # type: ignore[call-arg]


def test_listing_uuid_is_derived_from_the_natural_key() -> None:
    """Derived, so re-seeding is idempotent without a lookup and gate 1.6 stays byte-exact."""
    assert listing_uuid("mock_autobazaar", "AB-1001") == listing_uuid("mock_autobazaar", "AB-1001")
    assert listing_uuid("mock_autobazaar", "AB-1001") != listing_uuid("mock_drivenow", "AB-1001")
    assert isinstance(listing_uuid("a", "b"), uuid.UUID)
