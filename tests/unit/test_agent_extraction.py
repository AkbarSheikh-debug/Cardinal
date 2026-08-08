"""`DemoSlotExtractor` and `apply_updates` (PHASE-3 §5's DEMO_MODE stand-in for the live
haiku extraction call -- see `src/agent/extraction.py`'s module docstring).
"""

from __future__ import annotations

from datetime import date

import pytest

from src.agent.extraction import DemoSlotExtractor, apply_updates
from src.domain.enums import OfferType, VehicleCategory
from src.domain.money import Money
from src.domain.profile import RequirementProfile


@pytest.fixture
def extractor() -> DemoSlotExtractor:
    return DemoSlotExtractor()


async def test_extracts_goal_category_budget_date_from_one_message(
    extractor: DemoSlotExtractor,
) -> None:
    profile = RequirementProfile()
    updates = await extractor.extract(
        "I want to buy a suv, budget is 25000 euros, need it by 2026-09-15", profile
    )
    fields = {u.field for u in updates}
    assert fields == {"goal", "category", "budget", "target_date"}

    applied = apply_updates(profile, updates, turn=1)
    assert applied.goal.value is OfferType.BUY
    assert applied.category.value == [VehicleCategory.SUV]
    assert applied.budget.value == Money.of("25000")
    assert applied.target_date.value == date(2026, 9, 15)
    assert applied.is_complete


async def test_extracts_rent_goal(extractor: DemoSlotExtractor) -> None:
    profile = RequirementProfile()
    updates = await extractor.extract("I'm looking to rent something", profile)
    applied = apply_updates(profile, updates, turn=1)
    assert applied.goal.value is OfferType.RENT


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        # The contrast form. Goal matching is first-pattern-wins over a fixed rent-then-buy
        # order, so without negation stripping every one of these extracts the *ruled-out*
        # option -- which is how "Family Fatima" (tests/fixtures/demo/personas.json) silently
        # researched rentals for a buyer. Gate 3.1 only asserts the profile becomes complete,
        # never that a slot holds the right value, so it stayed green throughout.
        ("we're planning to buy, not rent", OfferType.BUY),
        ("I want to rent, not buy", OfferType.RENT),
        ("I would rather buy than rent", OfferType.BUY),
        ("I'd rather rent than buy", OfferType.RENT),
        ("looking to buy instead of renting", OfferType.BUY),
        # Explicitly undecided -- these have to be checked before the bare rent/buy keywords
        # they contain, or they can never match at all.
        ("not sure whether to rent or buy", OfferType.BOTH),
        ("should I rent or buy?", OfferType.BOTH),
        ("open to either", OfferType.BOTH),
        # Unambiguous statements, and one where "both" is incidental rather than the goal.
        ("I want to buy a suv", OfferType.BUY),
        ("both my wife and I want to rent a van", OfferType.RENT),
        ("I'm looking to lease", OfferType.RENT),
    ],
)
async def test_goal_extraction_reads_the_stated_option_not_the_ruled_out_one(
    extractor: DemoSlotExtractor, utterance: str, expected: OfferType
) -> None:
    profile = RequirementProfile()
    updates = await extractor.extract(utterance, profile)
    applied = apply_updates(profile, updates, turn=1)
    assert applied.goal.value is expected


async def test_partial_message_only_updates_mentioned_slots(
    extractor: DemoSlotExtractor,
) -> None:
    profile = RequirementProfile()
    updates = await extractor.extract("a hatchback please", profile)
    fields = {u.field for u in updates}
    assert fields == {"category"}


async def test_explicit_statement_locks_the_slot(extractor: DemoSlotExtractor) -> None:
    profile = RequirementProfile()
    updates = await extractor.extract("my budget is 20000 euros", profile)
    applied = apply_updates(profile, updates, turn=1)
    assert applied.budget.locked is True


async def test_locked_slot_is_not_overwritten_by_a_later_unlocked_inference(
    extractor: DemoSlotExtractor,
) -> None:
    profile = RequirementProfile()
    profile.budget = profile.budget.fill(Money.of("20000"), confidence=0.95, turn=1, locked=True)
    # No locking language this time -- should not move the already-locked budget.
    updates = await extractor.extract("maybe something around 30000 euros?", profile)
    applied = apply_updates(profile, updates, turn=2)
    assert applied.budget.value == Money.of("20000")


async def test_family_car_maps_to_suv_and_van_categories(extractor: DemoSlotExtractor) -> None:
    profile = RequirementProfile()
    updates = await extractor.extract("we need a family car", profile)
    applied = apply_updates(profile, updates, turn=1)
    assert applied.category.value is not None
    assert VehicleCategory.SUV in applied.category.value
    assert VehicleCategory.VAN_MPV in applied.category.value


async def test_no_matching_content_returns_no_updates(extractor: DemoSlotExtractor) -> None:
    profile = RequirementProfile()
    updates = await extractor.extract("hello there", profile)
    assert updates == ()
