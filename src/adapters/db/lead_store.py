"""`PostgresLeadStore` -- the durable path for `src/adapters/lead_store.py`'s `LeadStore`.

Dual storage, the shape D-006 established: `tier`/`score`/`state`/`dealer_id` are projected
columns the console sorts and filters on, and `canonical` is the full `Lead` -- score
breakdown, signal explanations and all -- that a row is rebuilt from. The breakdown must
survive a restart *as written*: recomputing it on read would show a dealer reasoning that
disagrees with the tier the lead was actually scored with, the moment a day passes and the
target date moves closer.

`dealer_id` is in the WHERE clause of every read, inside the SQL rather than filtered in
Python afterwards (CONSTITUTION IV.4, gate 15.5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.models import LeadRow
from src.adapters.lead_store import ScoreFn
from src.domain.lead import Lead, LeadEvent, LeadState, lead_uuid


def _to_lead(row: LeadRow) -> Lead:
    return Lead.model_validate(row.canonical)


def _row_values(lead: Lead) -> dict[str, object]:
    return {
        "id": lead.id,
        "buyer_account_id": lead.buyer_account_id,
        "dealer_id": lead.dealer_id,
        "listing_id": lead.listing_id,
        "tier": lead.score.tier.value,
        "score": lead.score.score,
        "state": lead.state.value,
        "canonical": lead.model_dump(mode="json"),
        "created_at": lead.created_at,
        "updated_at": lead.updated_at,
    }


class PostgresLeadStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def for_dealer(self, dealer_id: uuid.UUID) -> tuple[Lead, ...]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(LeadRow)
                .where(LeadRow.dealer_id == dealer_id)
                .order_by(LeadRow.created_at, LeadRow.id)
            )
            return tuple(_to_lead(row) for row in rows)

    async def get(self, dealer_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        async with self._sessions() as session:
            row = (
                await session.scalars(
                    select(LeadRow).where(LeadRow.id == lead_id, LeadRow.dealer_id == dealer_id)
                )
            ).first()
            return _to_lead(row) if row is not None else None

    async def record_event(
        self,
        *,
        buyer_account_id: uuid.UUID,
        dealer_id: uuid.UUID,
        listing_id: uuid.UUID,
        source: str,
        source_id: str,
        requirement_summary: str,
        event: LeadEvent,
        score_with: ScoreFn,
        now: datetime | None = None,
    ) -> tuple[Lead, bool]:
        """Read-modify-write in one session, then an idempotent upsert.

        Not a single `INSERT ... ON CONFLICT DO UPDATE` with SQL-side merging: the new score
        depends on the *accumulated* event set and on `score_with`, a Python callable, so the
        merge has to happen in Python. The upsert is still `ON CONFLICT` rather than a
        conditional insert, because two concurrent cart-adds for the same car would otherwise
        race between the SELECT and the INSERT and one would 500 on the primary key.
        """
        moment = now or datetime.now(UTC)
        lead_id = lead_uuid(buyer_account_id, listing_id)

        async with self._sessions() as session:
            existing_row = (
                await session.scalars(select(LeadRow).where(LeadRow.id == lead_id))
            ).first()
            existing = _to_lead(existing_row) if existing_row is not None else None

            if existing is None:
                lead = Lead(
                    id=lead_id,
                    buyer_account_id=buyer_account_id,
                    dealer_id=dealer_id,
                    listing_id=listing_id,
                    source=source,
                    source_id=source_id,
                    requirement_summary=requirement_summary,
                    events=(event,),
                    score=score_with((event,)),
                    created_at=moment,
                    updated_at=moment,
                )
                is_new = True
            else:
                events = existing.events if event in existing.events else (*existing.events, event)
                lead = existing.with_event(event, score=score_with(events), now=moment)
                if requirement_summary and requirement_summary != lead.requirement_summary:
                    lead = lead.model_copy(
                        update={"requirement_summary": requirement_summary, "updated_at": moment}
                    )
                is_new = False

            values = _row_values(lead)
            await session.execute(
                pg_insert(LeadRow)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[LeadRow.id],
                    set_={
                        k: values[k] for k in ("tier", "score", "state", "canonical", "updated_at")
                    },
                )
            )
            await session.commit()
            return lead, is_new

    async def set_state(
        self,
        dealer_id: uuid.UUID,
        lead_id: uuid.UUID,
        state: LeadState,
        *,
        now: datetime | None = None,
    ) -> Lead | None:
        moment = now or datetime.now(UTC)
        async with self._sessions() as session:
            row = (
                await session.scalars(
                    select(LeadRow).where(LeadRow.id == lead_id, LeadRow.dealer_id == dealer_id)
                )
            ).first()
            if row is None:
                return None
            updated = _to_lead(row).with_state(state, now=moment)
            row.state = updated.state.value
            row.canonical = updated.model_dump(mode="json")
            row.updated_at = updated.updated_at
            await session.commit()
            return updated
