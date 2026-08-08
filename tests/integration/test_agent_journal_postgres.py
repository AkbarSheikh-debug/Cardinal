"""Gate 4.3's durable sibling: `PostgresDecisionJournal` reuses the `decisions` table P0
pre-created (`migrations/0001_initial_schema`, DECISIONS.md D-014's table-per-phase
precedent). The journal is append-only -- there is no update path to test the absence of,
only that two writes to the same session both survive as distinct rows.

`decisions.session_id` carries a real `ON DELETE CASCADE` foreign key to `sessions.id`
(`migrations/0001_initial_schema.py`), so every test here creates a bare `SessionRow` first --
in a live session this is `PostgresSessionStateStore.save`, already called well before
RECOMMEND writes a decision.

Skipped when `CARDINAL_DATABASE_URL` is unset, same convention as
`test_agent_session_store_postgres.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from src.adapters.db.models import SessionRow
from src.adapters.db.session import dispose_engine, session_factory
from src.agent.journal import PostgresDecisionJournal, compute_inputs_hash, explain
from src.domain.memory import DecisionEntry, DecisionKind

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
async def _cleanup_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()


async def _ensure_session_row(session_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    async with session_factory()() as session:
        session.add(
            SessionRow(
                id=session_id,
                user_id="journal-test",
                phase="research",
                profile={},
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


def _entry(
    session_id: uuid.UUID, *, turn: int, kind: DecisionKind, rationale: str
) -> DecisionEntry:
    return DecisionEntry(
        id=uuid.uuid4(),
        session_id=session_id,
        turn=turn,
        kind=kind,
        inputs_hash=compute_inputs_hash({"session": str(session_id), "turn": turn}),
        weights={"price": 0.6, "mileage": 0.4},
        outcome={"selected": "mock_autobazaar:AB-1001"},
        rationale=rationale,
        ts=datetime.now(UTC),
    )


async def test_recorded_entry_round_trips_through_a_fresh_journal_instance(
    database_url_or_skip: str,
) -> None:
    session_id = uuid.uuid4()
    await _ensure_session_row(session_id)
    original = _entry(
        session_id, turn=3, kind=DecisionKind.RECOMMENDATION_MADE, rationale="first surviving pick"
    )

    writer = PostgresDecisionJournal(session_factory())
    await writer.record(original)

    reader = PostgresDecisionJournal(session_factory())
    restored = await reader.latest_by_kind(session_id, DecisionKind.RECOMMENDATION_MADE)

    assert restored is not None
    assert restored.rationale == original.rationale
    assert restored.inputs_hash == original.inputs_hash
    assert restored.weights == original.weights
    assert restored.outcome == original.outcome


async def test_journal_is_append_only_and_for_session_returns_every_row_in_turn_order(
    database_url_or_skip: str,
) -> None:
    session_id = uuid.uuid4()
    await _ensure_session_row(session_id)
    journal = PostgresDecisionJournal(session_factory())
    await journal.record(
        _entry(
            session_id, turn=2, kind=DecisionKind.FILTER_APPLIED, rationale="hard filters applied"
        )
    )
    await journal.record(
        _entry(session_id, turn=5, kind=DecisionKind.RECOMMENDATION_MADE, rationale="first pick")
    )
    await journal.record(
        _entry(
            session_id, turn=8, kind=DecisionKind.RECOMMENDATION_MADE, rationale="re-ranked pick"
        )
    )

    entries = await journal.for_session(session_id)
    assert [e.turn for e in entries] == [2, 5, 8]

    latest = await journal.latest_by_kind(session_id, DecisionKind.RECOMMENDATION_MADE)
    assert latest is not None
    assert latest.rationale == "re-ranked pick"


async def test_explain_answers_from_the_recorded_row_with_no_recomputation(
    database_url_or_skip: str,
) -> None:
    session_id = uuid.uuid4()
    await _ensure_session_row(session_id)
    journal = PostgresDecisionJournal(session_factory())
    rationale = "AB-1034 selected as the first candidate surviving hard filters."
    await journal.record(
        _entry(session_id, turn=4, kind=DecisionKind.RECOMMENDATION_MADE, rationale=rationale)
    )

    answer = await explain(journal, session_id, kind=DecisionKind.RECOMMENDATION_MADE)
    assert answer == rationale


async def test_two_sessions_journals_do_not_cross_contaminate(database_url_or_skip: str) -> None:
    journal = PostgresDecisionJournal(session_factory())
    session_a, session_b = uuid.uuid4(), uuid.uuid4()
    await _ensure_session_row(session_a)
    await _ensure_session_row(session_b)
    await journal.record(
        _entry(session_a, turn=1, kind=DecisionKind.RECOMMENDATION_MADE, rationale="A's pick")
    )
    await journal.record(
        _entry(session_b, turn=1, kind=DecisionKind.RECOMMENDATION_MADE, rationale="B's pick")
    )

    entries_a = await journal.for_session(session_a)
    assert len(entries_a) == 1
    assert entries_a[0].rationale == "A's pick"
