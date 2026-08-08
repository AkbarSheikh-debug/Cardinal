"""`DateRange` lives on its own because both booking (P8) and availability (P1) need it,
and neither should have to import the other to get it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class DateRange(BaseModel):
    """Inclusive on both ends."""

    model_config = ConfigDict(frozen=True)

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError(f"date range end {self.end} precedes start {self.start}")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def overlaps(self, other: DateRange) -> bool:
        return self.start <= other.end and other.start <= self.end

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def intersect(self, other: DateRange) -> DateRange | None:
        if not self.overlaps(other):
            return None
        return DateRange(start=max(self.start, other.start), end=min(self.end, other.end))

    def subtract(self, blocked: DateRange) -> tuple[DateRange, ...]:
        """The parts of this range not covered by `blocked`.

        Returns 0, 1 or 2 ranges -- a block in the middle splits the window in two, which is
        exactly the case a rental availability check has to get right.
        """
        if not self.overlaps(blocked):
            return (self,)
        parts: list[DateRange] = []
        if blocked.start > self.start:
            parts.append(DateRange(start=self.start, end=blocked.start - timedelta(days=1)))
        if blocked.end < self.end:
            parts.append(DateRange(start=blocked.end + timedelta(days=1), end=self.end))
        return tuple(parts)
