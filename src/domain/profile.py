"""Interview state.

PLAN-00 §6.3: working state is code-owned, not model-owned. "The model remembers" degrades
under context pressure; a typed profile with per-slot value, confidence and provenance does
not, and it makes P6's progress surface trivially derivable rather than re-inferred.
"""

from __future__ import annotations

from datetime import date
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import OfferType, VehicleCategory
from src.domain.money import Money


class Slot[T](BaseModel):
    """One elicited fact, with how sure we are and which turn produced it."""

    model_config = ConfigDict(frozen=True)

    value: T | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_turn: int = Field(default=0, ge=0)
    locked: bool = Field(
        default=False,
        description="Set when the user states it outright. A locked slot is never overwritten "
        "by inference -- that is the failure where a stated budget silently drifts.",
    )

    @property
    def is_filled(self) -> bool:
        return self.value is not None

    def fill(self, value: T, *, confidence: float, turn: int, locked: bool = False) -> Self:
        if self.locked and not locked:
            return self
        return type(self)(value=value, confidence=confidence, source_turn=turn, locked=locked)


class HardFilter(BaseModel):
    """A stated constraint that removes rows.

    PHASE-5 §4: hard filters run *before* scoring, never as a zero weight. "Nothing over
    80,000 km" removes candidates; conflating that with a penalty is how a demo surfaces a
    96k-km car with a good score and looks broken.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    operator: str = Field(pattern=r"^(lte|gte|eq|in|not_in)$")
    value: str | int | float | list[str] | list[int]


class RequirementProfile(BaseModel):
    """Mutable by design -- it accumulates across the interview."""

    model_config = ConfigDict(validate_assignment=True)

    goal: Slot[OfferType] = Field(default_factory=Slot[OfferType])
    category: Slot[list[VehicleCategory]] = Field(default_factory=Slot[list[VehicleCategory]])
    budget: Slot[Money] = Field(default_factory=Slot[Money])
    target_date: Slot[date] = Field(default_factory=Slot[date])
    horizon_months: Slot[int] = Field(default_factory=Slot[int])
    use_case: Slot[str] = Field(default_factory=Slot[str])
    hard_filters: list[HardFilter] = Field(default_factory=list)

    #: The slots an interview must fill before research may begin. `ClassVar`, not a bare
    #: annotation -- pydantic would otherwise make this a *field* with a default, which
    #: puts it in `model_dump()` and makes class-level access raise.
    REQUIRED: ClassVar[tuple[str, ...]] = ("goal", "category", "budget", "target_date")

    @property
    def completeness(self) -> float:
        filled = sum(1 for name in self.REQUIRED if getattr(self, name).is_filled)
        return filled / len(self.REQUIRED)

    @property
    def is_complete(self) -> bool:
        return self.completeness == 1.0

    def missing_slots(self) -> list[str]:
        return [name for name in self.REQUIRED if not getattr(self, name).is_filled]
