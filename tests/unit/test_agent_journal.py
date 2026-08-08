"""The decision journal (PHASE-4 §3.4): append-only, answers "why X over Y" from a recorded
row with zero model calls (gate 4.3), and locked-slot resistance to later inference (gate 4.2,
PHASE-4 §3.1) as a domain-level property, not just something the gate happens to demonstrate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.agent.extraction import SlotUpdate, apply_updates
from src.agent.journal import InMemoryDecisionJournal, compute_inputs_hash, explain, session_uuid
from src.domain.enums import VehicleCategory
from src.domain.memory import DecisionEntry, DecisionKind
from src.domain.money import Money
from src.domain.profile import RequirementProfile


def _entry(
    session_id: uuid.UUID, *, turn: int, kind: DecisionKind, rationale: str
) -> DecisionEntry:
    return DecisionEntry(
        id=uuid.uuid4(),
        session_id=session_id,
        turn=turn,
        kind=kind,
        inputs_hash=compute_inputs_hash({"turn": turn}),
        rationale=rationale,
        ts=datetime.now(UTC),
    )


# -- session_uuid -----------------------------------------------------------------------


def test_session_uuid_passes_through_a_real_uuid_string() -> None:
    real = str(uuid.uuid4())
    assert str(session_uuid(real)) == real


def test_session_uuid_derives_deterministically_from_a_non_uuid_string() -> None:
    first = session_uuid("gate31-not-a-uuid")
    second = session_uuid("gate31-not-a-uuid")
    other = session_uuid("gate31-different")
    assert first == second
    assert first != other


# -- InMemoryDecisionJournal --------------------------------------------------------------


async def test_record_then_for_session_returns_only_that_sessions_entries() -> None:
    journal = InMemoryDecisionJournal()
    mine = uuid.uuid4()
    theirs = uuid.uuid4()
    await journal.record(_entry(mine, turn=1, kind=DecisionKind.FILTER_APPLIED, rationale="a"))
    await journal.record(_entry(theirs, turn=1, kind=DecisionKind.FILTER_APPLIED, rationale="b"))

    mine_entries = await journal.for_session(mine)
    assert len(mine_entries) == 1
    assert mine_entries[0].rationale == "a"


async def test_latest_by_kind_returns_the_highest_turn_of_that_kind() -> None:
    journal = InMemoryDecisionJournal()
    session_id = uuid.uuid4()
    await journal.record(
        _entry(session_id, turn=2, kind=DecisionKind.RECOMMENDATION_MADE, rationale="first pick")
    )
    await journal.record(
        _entry(session_id, turn=5, kind=DecisionKind.RECOMMENDATION_MADE, rationale="revised pick")
    )
    await journal.record(
        _entry(session_id, turn=9, kind=DecisionKind.FILTER_APPLIED, rationale="unrelated")
    )

    latest = await journal.latest_by_kind(session_id, DecisionKind.RECOMMENDATION_MADE)
    assert latest is not None
    assert latest.rationale == "revised pick"


async def test_latest_by_kind_returns_none_when_nothing_of_that_kind_was_recorded() -> None:
    journal = InMemoryDecisionJournal()
    assert await journal.latest_by_kind(uuid.uuid4(), DecisionKind.WEIGHTS_CHOSEN) is None


# -- explain() ------------------------------------------------------------------------------


async def test_explain_returns_the_stored_rationale_verbatim() -> None:
    journal = InMemoryDecisionJournal()
    session_id = uuid.uuid4()
    rationale = "AB-1034 selected as the first candidate surviving hard filters."
    await journal.record(
        _entry(session_id, turn=4, kind=DecisionKind.RECOMMENDATION_MADE, rationale=rationale)
    )

    answer = await explain(journal, session_id, kind=DecisionKind.RECOMMENDATION_MADE)
    assert answer == rationale


async def test_explain_returns_none_when_the_journal_has_nothing_for_that_session() -> None:
    journal = InMemoryDecisionJournal()
    answer = await explain(journal, uuid.uuid4(), kind=DecisionKind.RECOMMENDATION_MADE)
    assert answer is None


# -- inputs_hash --------------------------------------------------------------------------


def test_compute_inputs_hash_is_stable_regardless_of_key_order() -> None:
    a = compute_inputs_hash({"x": 1, "y": 2})
    b = compute_inputs_hash({"y": 2, "x": 1})
    assert a == b


def test_compute_inputs_hash_differs_on_different_payloads() -> None:
    a = compute_inputs_hash({"x": 1})
    b = compute_inputs_hash({"x": 2})
    assert a != b


# -- locked-slot resistance (PHASE-4 §3.1, gate 4.2) ---------------------------------------


def test_locked_slot_is_not_overwritten_by_a_later_lower_confidence_inference() -> None:
    profile = RequirementProfile()
    locked = apply_updates(profile, (SlotUpdate("budget", Money.of("28000"), 0.95, True),), turn=1)

    drifted = apply_updates(locked, (SlotUpdate("budget", Money.of("45000"), 0.4, False),), turn=9)

    assert drifted.budget.value == Money.of("28000")
    assert drifted.budget.locked
    assert drifted.budget.source_turn == 1


def test_locked_slot_can_only_be_overwritten_by_another_explicit_locked_statement() -> None:
    profile = RequirementProfile()
    locked = apply_updates(profile, (SlotUpdate("budget", Money.of("28000"), 0.95, True),), turn=1)

    restated = apply_updates(locked, (SlotUpdate("budget", Money.of("45000"), 0.9, True),), turn=9)

    assert restated.budget.value == Money.of("45000")
    assert restated.budget.source_turn == 9


def test_unlocked_slots_are_unaffected_by_a_sibling_slots_lock() -> None:
    profile = RequirementProfile()
    locked = apply_updates(profile, (SlotUpdate("budget", Money.of("28000"), 0.95, True),), turn=1)

    updated = apply_updates(
        locked, (SlotUpdate("category", [VehicleCategory.LUXURY], 0.4, False),), turn=9
    )

    assert updated.category.value == [VehicleCategory.LUXURY]
    assert updated.category.locked is False
