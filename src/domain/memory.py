"""Memory and decision-journal contracts. P4 and P9 fill these in.

`MemoryRecord` supersedes rather than updates, and `DecisionEntry` is append-only. Both for
the same reason: "why did it recommend that?" is unanswerable if the inputs were mutated
after the fact.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryKind(StrEnum):
    PREFERENCE = "preference"
    REJECTION = "rejection"
    CONSTRAINT = "constraint"
    FACT = "fact"


class MemoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    user_id: str = Field(min_length=1)
    kind: MemoryKind
    body: str = Field(min_length=1)
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Which session and turn produced this. A memory with no provenance cannot "
        "be defended to the user when they ask why the agent thinks it.",
    )
    created_at: datetime
    superseded_by: uuid.UUID | None = None

    @property
    def is_current(self) -> bool:
        return self.superseded_by is None


class DecisionKind(StrEnum):
    WEIGHTS_CHOSEN = "weights_chosen"
    RANKING_PRODUCED = "ranking_produced"
    FILTER_APPLIED = "filter_applied"
    RECOMMENDATION_MADE = "recommendation_made"


class DecisionEntry(BaseModel):
    """Append-only. `inputs_hash` is what makes a ranking reproducible after the fact:
    re-run with the same hash and the same seed, get the same outcome (CONSTITUTION II.2).
    """

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    session_id: uuid.UUID
    turn: int = Field(ge=0)
    kind: DecisionKind
    inputs_hash: str = Field(min_length=8)
    weights: dict[str, float] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    ts: datetime
