"""Durable `SessionState` (PHASE-3 §8 gate 3.2: restart-resume recovers phase + profile
exactly).

Not to be confused with the Claude Agent SDK's own `SessionStore` protocol
(`claude_agent_sdk.types.SessionStore`), which mirrors the CLI's raw conversation transcript
for replay. That is orthogonal to this: our `SessionState` is the typed, code-owned phase +
`RequirementProfile` (PLAN-00 §6.3), and it is what a judge restarting the process mid-demo
needs recovered, not the transcript.

Reuses the `sessions` table P0 pre-created for this phase (`migrations/0001_initial_schema`)
-- see DECISIONS.md D-014 for why the whole `SessionState` (not just `RequirementProfile`)
lives in that table's `profile` JSONB column.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.models import SessionRow
from src.agent.phase_machine import SessionState


class SessionStateStore(Protocol):
    async def save(self, state: SessionState, *, user_id: str = "demo") -> None: ...

    async def load(self, session_id: str) -> SessionState | None: ...


class InMemorySessionStateStore:
    """Used by `DEMO_MODE` and by unit tests -- no container required."""

    def __init__(self) -> None:
        self._states: dict[str, SessionState] = {}

    async def save(self, state: SessionState, *, user_id: str = "demo") -> None:
        self._states[state.session_id] = state

    async def load(self, session_id: str) -> SessionState | None:
        return self._states.get(session_id)


class PostgresSessionStateStore:
    """The durable path (gate 3.2). `session_id` must be a UUID string -- it is the
    `sessions` table's primary key.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, state: SessionState, *, user_id: str = "demo") -> None:
        session_pk = uuid.UUID(state.session_id)
        payload = state.model_dump(mode="json")
        now = datetime.now(UTC)

        async with self._sessions() as session:
            row = await session.get(SessionRow, session_pk)
            if row is None:
                session.add(
                    SessionRow(
                        id=session_pk,
                        user_id=user_id,
                        phase=state.phase.value,
                        profile=payload,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.phase = state.phase.value
                row.profile = payload
                row.updated_at = now
            await session.commit()

    async def load(self, session_id: str) -> SessionState | None:
        session_pk = uuid.UUID(session_id)
        async with self._sessions() as session:
            row = await session.scalar(select(SessionRow).where(SessionRow.id == session_pk))
        if row is None:
            return None
        return SessionState.model_validate(row.profile)
