"""Gate 3.2: a session survives process restart -- resume by `session_id` recovers phase and
profile exactly. `PostgresSessionStateStore` reuses the `sessions` table P0 pre-created
(DECISIONS.md D-014).

Skipped when `CARDINAL_DATABASE_URL` is unset, so `make test` stays runnable with no
container; the gate runs it with one, same pattern as `test_postgres_store.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest

from src.adapters.db.session import dispose_engine, session_factory
from src.agent.phase_machine import Phase, SessionState, new_session
from src.agent.session_store import PostgresSessionStateStore
from src.domain.enums import OfferType, VehicleCategory
from src.domain.money import Money

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
async def _cleanup_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()


def _in_progress_state() -> SessionState:
    state = new_session(str(uuid.uuid4()))
    profile = state.profile
    profile.goal = profile.goal.fill(OfferType.BUY, confidence=0.9, turn=1, locked=True)
    profile.category = profile.category.fill(
        [VehicleCategory.SUV, VehicleCategory.CROSSOVER], confidence=0.8, turn=2
    )
    profile.budget = profile.budget.fill(Money.of("27500.50"), confidence=0.95, turn=3, locked=True)
    profile.target_date = profile.target_date.fill(date(2026, 10, 1), confidence=0.7, turn=3)
    return state.model_copy(
        update={
            "phase": Phase.RESEARCH,
            "turn_in_phase": 2,
            "total_turns": 6,
            "profile": profile,
            "candidate_ids": ("mock_autobazaar:AB-1001", "mock_drivenow:DN-2002"),
        }
    )


async def test_save_then_load_recovers_phase_and_profile_exactly(
    database_url_or_skip: str,
) -> None:
    store = PostgresSessionStateStore(session_factory())
    original = _in_progress_state()

    await store.save(original, user_id="gate32-user")
    restored = await store.load(original.session_id)

    assert restored is not None
    assert restored.phase is Phase.RESEARCH
    assert restored == original


async def test_load_of_unknown_session_id_returns_none(database_url_or_skip: str) -> None:
    store = PostgresSessionStateStore(session_factory())
    assert await store.load(str(uuid.uuid4())) is None


async def test_save_is_idempotent_and_the_second_write_wins(database_url_or_skip: str) -> None:
    store = PostgresSessionStateStore(session_factory())
    original = _in_progress_state()
    await store.save(original, user_id="gate32-user")

    advanced = original.model_copy(
        update={"phase": Phase.RECOMMEND, "turn_in_phase": 0, "selected_candidate": "AB-1001"}
    )
    await store.save(advanced, user_id="gate32-user")

    restored = await store.load(original.session_id)
    assert restored is not None
    assert restored.phase is Phase.RECOMMEND
    assert restored.selected_candidate == "AB-1001"


async def test_a_fresh_store_instance_recovers_the_same_state(
    database_url_or_skip: str,
) -> None:
    """The literal restart-resume shape gate 3.2 describes: a *new* store object (standing
    in for a new process) sees what an earlier one wrote.
    """
    original = _in_progress_state()
    writer = PostgresSessionStateStore(session_factory())
    await writer.save(original, user_id="gate32-user")

    reader = PostgresSessionStateStore(session_factory())
    restored = await reader.load(original.session_id)

    assert restored == original
