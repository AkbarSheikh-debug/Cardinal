"""The decision journal (PHASE-4 §3.4): append-only, queryable, answers "why X over Y"
without re-deriving it.

Every ranking, filter application, and recommendation writes one `DecisionEntry` and never
updates it afterwards. The point isn't durability for its own sake -- it's that re-running a
ranking to answer "why did you pick that one?" can legitimately come out *differently*
phrased eight turns later, and that inconsistency is what makes a demo look unreliable
(PHASE-4 §3.4). `explain()` reads the stored `rationale` back verbatim instead, which is why
gate 4.3 can assert "zero model calls" structurally: nothing in this module ever calls a
model.

Same shape as `session_store.py`'s `SessionStateStore`: one protocol, an in-memory
implementation for `DEMO_MODE` and tests, a Postgres implementation reusing the `decisions`
table P0 pre-created (`migrations/0001_initial_schema`, DECISIONS.md D-014's table-per-phase
precedent).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.models import DecisionRow
from src.domain.memory import DecisionEntry, DecisionKind


def session_uuid(session_id: str) -> uuid.UUID:
    """`SessionState.session_id` is a plain string (PHASE-3 §3), not guaranteed parseable as
    a UUID -- persona/gate ids like `f"gate31-{uuid.uuid4()}"` aren't. `DecisionRow.session_id`
    is a real UUID column, so a non-UUID id is deterministically derived into one rather than
    raising; the same input always maps to the same UUID, which is all a foreign key needs.
    """
    try:
        return uuid.UUID(session_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, session_id)


def compute_inputs_hash(payload: Mapping[str, Any]) -> str:
    """A stable hash of whatever produced a decision. Lets a caller detect "same question,
    same inputs" and serve the recorded answer verbatim instead of recomputing it.
    """
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DecisionJournal(Protocol):
    async def record(self, entry: DecisionEntry) -> None: ...

    async def for_session(self, session_id: uuid.UUID) -> tuple[DecisionEntry, ...]: ...

    async def latest_by_kind(
        self, session_id: uuid.UUID, kind: DecisionKind
    ) -> DecisionEntry | None: ...


class InMemoryDecisionJournal:
    """Used by `DEMO_MODE` and by unit tests -- no container required."""

    def __init__(self) -> None:
        self._entries: list[DecisionEntry] = []

    async def record(self, entry: DecisionEntry) -> None:
        self._entries.append(entry)

    async def for_session(self, session_id: uuid.UUID) -> tuple[DecisionEntry, ...]:
        return tuple(e for e in self._entries if e.session_id == session_id)

    async def latest_by_kind(
        self, session_id: uuid.UUID, kind: DecisionKind
    ) -> DecisionEntry | None:
        matches = [e for e in self._entries if e.session_id == session_id and e.kind is kind]
        return max(matches, key=lambda e: e.turn, default=None)


class PostgresDecisionJournal:
    """The durable path (gate 4.1's sibling for the journal tier). Append-only: `record`
    always inserts, never updates -- there is no code path that mutates a `DecisionRow`.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, entry: DecisionEntry) -> None:
        async with self._sessions() as session:
            session.add(
                DecisionRow(
                    id=entry.id,
                    session_id=entry.session_id,
                    turn=entry.turn,
                    kind=entry.kind.value,
                    inputs_hash=entry.inputs_hash,
                    weights=entry.weights,
                    outcome=entry.outcome,
                    rationale=entry.rationale,
                    ts=entry.ts,
                )
            )
            await session.commit()

    async def for_session(self, session_id: uuid.UUID) -> tuple[DecisionEntry, ...]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(DecisionRow)
                .where(DecisionRow.session_id == session_id)
                .order_by(DecisionRow.turn)
            )
            return tuple(_to_entry(row) for row in rows)

    async def latest_by_kind(
        self, session_id: uuid.UUID, kind: DecisionKind
    ) -> DecisionEntry | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(DecisionRow)
                .where(DecisionRow.session_id == session_id, DecisionRow.kind == kind.value)
                .order_by(DecisionRow.turn.desc())
                .limit(1)
            )
        return _to_entry(row) if row is not None else None


def _to_entry(row: DecisionRow) -> DecisionEntry:
    return DecisionEntry(
        id=row.id,
        session_id=row.session_id,
        turn=row.turn,
        kind=DecisionKind(row.kind),
        inputs_hash=row.inputs_hash,
        weights=row.weights,
        outcome=row.outcome,
        rationale=row.rationale,
        ts=row.ts,
    )


async def explain(
    journal: DecisionJournal, session_id: uuid.UUID, *, kind: DecisionKind
) -> str | None:
    """ "Why X over Y" answered from the recorded row -- no re-derivation, no model call
    (PHASE-4 §3.4, gate 4.3). `None` only when nothing of that kind was ever recorded.
    """
    entry = await journal.latest_by_kind(session_id, kind)
    return entry.rationale if entry is not None else None
