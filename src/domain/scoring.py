"""Ranking contracts.

CONSTITUTION II.2: the model chooses weights, code computes scores. These types are the
seam between those two responsibilities. P5 fills them in; P0 only fixes their shape.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldRef(BaseModel):
    """The grounding primitive (CONSTITUTION II.3).

    Every quantitative claim in a rationale carries one of these. A rationale with an
    uncited figure is rejected and regenerated -- which eliminates the "the agent invented
    a statistic" failure, the one that ends a demo because a judge will check a number.
    """

    model_config = ConfigDict(frozen=True)

    listing_id: str
    field_name: str

    def __str__(self) -> str:
        return f"{self.listing_id}.{self.field_name}"


class CriterionWeight(BaseModel):
    model_config = ConfigDict(frozen=True)

    criterion: str = Field(min_length=1)
    weight: float = Field(ge=0.0, le=1.0)


class WeightSet(BaseModel):
    """Weights are normalised on construction, so a model that emits `{a: 3, b: 1}` and one
    that emits `{a: 0.75, b: 0.25}` produce identical rankings.
    """

    model_config = ConfigDict(frozen=True)

    weights: tuple[CriterionWeight, ...]

    @model_validator(mode="after")
    def _normalise(self) -> Self:
        total = sum(w.weight for w in self.weights)
        if total <= 0:
            raise ValueError("weight set must contain at least one positive weight")
        names = [w.criterion for w in self.weights]
        if len(set(names)) != len(names):
            raise ValueError("duplicate criterion in weight set")
        # Sorted by name so the same weights in a different order hash identically --
        # which is what makes `inputs_hash` on DecisionEntry meaningful.
        normalised = tuple(
            sorted(
                (
                    CriterionWeight(criterion=w.criterion, weight=w.weight / total)
                    for w in self.weights
                ),
                key=lambda w: w.criterion,
            )
        )
        object.__setattr__(self, "weights", normalised)
        return self

    def as_dict(self) -> dict[str, float]:
        return {w.criterion: w.weight for w in self.weights}


class CriterionScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    criterion: str
    weight: float = Field(ge=0.0, le=1.0)
    normalised_value: float = Field(ge=0.0, le=1.0)
    contribution: float

    @model_validator(mode="after")
    def _contribution_is_the_product(self) -> Self:
        expected = self.weight * self.normalised_value
        if abs(self.contribution - expected) > 1e-9:
            raise ValueError("contribution must equal weight x normalised_value")
        return self


class ScoreBreakdown(BaseModel):
    """Per-criterion detail plus the total.

    P6's stacked bar renders this directly -- no recomputation, so the chart cannot
    disagree with the ranking.
    """

    model_config = ConfigDict(frozen=True)

    criteria: tuple[CriterionScore, ...]
    total: float

    @model_validator(mode="after")
    def _total_is_the_sum(self) -> Self:
        expected = sum(c.contribution for c in self.criteria)
        if abs(self.total - expected) > 1e-9:
            raise ValueError("total must equal the sum of contributions")
        return self


class RankedResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    listing_id: uuid.UUID
    rank: int = Field(ge=1)
    breakdown: ScoreBreakdown
    rationale: str
    citations: tuple[FieldRef, ...] = ()


# ==============================================================================================
# Pure scoring math (PHASE-5 SS3-SS4). Everything below operates on primitives -- floats,
# strings, dates-as-day-counts -- never a `Listing`. That is what gate 5.9 pins ("zero imports
# outside stdlib + pydantic") and what makes it property-testable with no model, no fixtures,
# no event loop: a normalisation function here cannot accidentally depend on which adapter a
# row came from, only on the numbers it was handed. `src/domain/ranking.py` is the seam that
# reads a real `Listing` and calls into these.
# ==============================================================================================


class Criterion(StrEnum):
    """The five `[MVP]` criteria (PHASE-5 SS4). Fixed and closed -- PHASE-5 SS10's risk table
    calls for constraining weights to an enum so a model choosing criterion names can't drift
    between runs and quietly break determinism (gate 5.1). `condition` and `proximity` are
    PHASE-5 SS4's `[SCALE]` rows and are deliberately absent.
    """

    BUDGET_FIT = "budget_fit"
    RESALE_STRENGTH = "resale_strength"
    CATEGORY_MATCH = "category_match"
    AVAILABILITY = "availability"
    RUNNING_COST = "running_cost"


#: PHASE-5 SS3's own worked example. The model is free to choose different weights per
#: session; this is what a caller falls back to when none are supplied (DEMO_MODE, gates).
DEFAULT_WEIGHTS = WeightSet(
    weights=(
        CriterionWeight(criterion=Criterion.BUDGET_FIT, weight=0.25),
        CriterionWeight(criterion=Criterion.RESALE_STRENGTH, weight=0.30),
        CriterionWeight(criterion=Criterion.CATEGORY_MATCH, weight=0.20),
        CriterionWeight(criterion=Criterion.AVAILABILITY, weight=0.15),
        CriterionWeight(criterion=Criterion.RUNNING_COST, weight=0.10),
    )
)


def normalise_budget_fit(price: float, ceiling: float) -> float:
    """Piecewise: 1.0 at <=80% of ceiling, linear decay to 0 at the ceiling, hard 0 above it.

    The cliff at `ceiling` is deliberate -- PHASE-5 SS4: "a hard limit is hard, don't smooth
    over it." (Candidates already over budget are normally removed as a hard filter before
    scoring ever runs; this cliff is a defensive invariant of the criterion itself, not the
    only place the limit is enforced.)
    """
    if ceiling <= 0:
        raise ValueError("a budget ceiling must be positive")
    if price > ceiling:
        return 0.0
    threshold = 0.8 * ceiling
    if price <= threshold:
        return 1.0
    return (ceiling - price) / (ceiling - threshold)


def normalise_resale_strength(retained_fraction: float) -> float:
    """`retained_fraction` is a point off a `depreciation_curve` -- already in (0, 1], but
    clamped defensively since this function has no way to know that on its own.
    """
    return max(0.0, min(1.0, retained_fraction))


def normalise_category_match(
    category: str, requested: Sequence[str], *, locked: bool, confidence: float
) -> float:
    """Set overlap, weighted by explicit vs inferred (PHASE-5 SS4): a match against a locked
    (explicitly stated) preference always scores 1.0; a match against an inferred one scores
    proportional to how confident the inference was, with a floor so a weak inference still
    counts for something. No stated preference at all is not a mismatch -- nothing to miss.
    """
    if not requested:
        return 1.0
    if category not in requested:
        return 0.0
    return 1.0 if locked else max(0.5, min(1.0, confidence))


#: Available this many days or more before the target date scores full marks; the last
#: stretch decays linearly. A car that only clears the deadline by a day or two carries real
#: handover/registration risk, which is the "decaying" PHASE-5 SS4 calls for alongside the
#: negative-gap hard zero (DECISIONS.md D-020).
AVAILABILITY_BUFFER_DAYS = 14


def normalise_availability(gap_days: int, *, buffer_days: int = AVAILABILITY_BUFFER_DAYS) -> float:
    """`gap_days` = target_date - available_from. Negative (available after the date the
    buyer needs it) is a hard 0, per PHASE-5 SS4.
    """
    if gap_days < 0:
        return 0.0
    if buffer_days <= 0:
        return 1.0
    return max(0.0, min(1.0, gap_days / buffer_days))


def zscore(value: float, population: Sequence[float]) -> float:
    """0.0 for a population too small to have a meaningful spread, rather than dividing by a
    zero or near-zero sample standard deviation.
    """
    if len(population) < 2:
        return 0.0
    mean: float = sum(population) / len(population)
    variance: float = sum((x - mean) ** 2 for x in population) / len(population)
    std: float = variance**0.5
    if std == 0:
        return 0.0
    return (value - mean) / std


def normalise_running_cost(cost: float, population: Sequence[float]) -> float:
    """Relative to the candidate set, never absolute (PHASE-5 SS4) -- an absolute EUR/month
    figure means nothing without the peer group it's being compared inside. Two standard
    deviations below the set's mean scores 1.0; two above scores 0.0.
    """
    z = zscore(cost, population)
    return max(0.0, min(1.0, 0.5 - z * 0.25))


def score_breakdown(weights: WeightSet, normalised_values: Mapping[str, float]) -> ScoreBreakdown:
    """Assembles the per-criterion detail plus the total that P6's stacked bar renders
    directly (PHASE-5 SS4) -- `ScoreBreakdown`'s own validators (gate 5.2) guarantee the
    contributions sum to the total, so there is nothing left for a caller to get wrong here.
    """
    criteria = []
    for weight in weights.weights:
        if weight.criterion not in normalised_values:
            raise KeyError(f"no normalised value supplied for criterion {weight.criterion!r}")
        value = max(0.0, min(1.0, normalised_values[weight.criterion]))
        criteria.append(
            CriterionScore(
                criterion=weight.criterion,
                weight=weight.weight,
                normalised_value=value,
                contribution=weight.weight * value,
            )
        )
    total = sum(c.contribution for c in criteria)
    return ScoreBreakdown(criteria=tuple(criteria), total=total)


def ranking_sort_key(score: float, listing_id: uuid.UUID | str) -> tuple[float, str]:
    """Highest score first, ties broken on `listing_id` -- never insertion order
    (CONSTITUTION II.2, gate 5.1).
    """
    return (-score, str(listing_id))


# -- grounding (PHASE-5 SS6, CONSTITUTION II.3) -----------------------------------------------
# Text-only: pulling numbers out of a rationale string needs no `Listing`. Checking those
# numbers against a listing's actual field values does, so that half lives in `ranking.py`.

_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str) -> tuple[float, ...]:
    """Every bare number in a rationale -- what the grounding validator checks against cited
    fields. Currency symbols and percent signs are simply not part of the match; the number
    itself is what's asserted, not its unit.
    """
    return tuple(float(m.replace(",", "")) for m in _NUMBER_PATTERN.findall(text))
