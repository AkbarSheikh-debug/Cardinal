"""The ranking engine (PHASE-5 SS3-SS4, SS6, SS8): the seam that reads a real `Listing` and a
`RequirementProfile` and calls into `src/domain/scoring.py`'s pure math to produce
`RankedResult`s.

CONSTITUTION II.2 ("the model chooses weights, code computes scores") lives here: `rank()`
takes whatever `WeightSet` a session settled on (or `DEFAULT_WEIGHTS` for `DEMO_MODE` and the
gates) and is otherwise a pure function of its inputs -- no clock, no randomness, no I/O --
so the same profile, candidates and weights always produce the same order (gate 5.1).

Three PHASE-5 mechanisms live in this module rather than `scoring.py`, because all three need
to read `Listing` fields, which `scoring.py` is not allowed to import (gate 5.9):

- Hard filtering (SS4): a stated constraint removes a row outright, before scoring runs.
- Grounding (SS6): every number in a rationale must trace to a cited listing field.
- The critic pass (SS8): a second, independent check of the top N against every hard filter
  and the stated budget, reading full listings rather than trusting the ranking pass.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.domain.costs import monthly_running_cost
from src.domain.enums import OfferType
from src.domain.listing import Listing
from src.domain.money import Money
from src.domain.profile import HardFilter, RequirementProfile
from src.domain.scoring import (
    DEFAULT_WEIGHTS,
    Criterion,
    FieldRef,
    RankedResult,
    ScoreBreakdown,
    WeightSet,
    extract_numbers,
    normalise_availability,
    normalise_budget_fit,
    normalise_category_match,
    normalise_resale_strength,
    normalise_running_cost,
    ranking_sort_key,
    score_breakdown,
)

#: When `RequirementProfile.horizon_months` was never filled -- it isn't a `REQUIRED` slot
#: (PHASE-0's `profile.py`) -- resale strength and running-cost scoring still need *some*
#: horizon to evaluate against. One year is the plan's own example horizon (PHASE-5 SS5).
DEFAULT_HORIZON_MONTHS = 12

UNVERIFIED_MARKER = "[unverified]"

_CRITERION_LABELS: dict[str, str] = {
    Criterion.BUDGET_FIT: "budget fit",
    Criterion.RESALE_STRENGTH: "resale strength",
    Criterion.CATEGORY_MATCH: "category match",
    Criterion.AVAILABILITY: "availability",
    Criterion.RUNNING_COST: "running cost",
}


# -- hard filters (PHASE-5 SS4) -----------------------------------------------------------------

_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "lte": lambda a, b: a <= b,
    "gte": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


def _field_value(listing: Listing, field: str) -> Any:
    value = getattr(listing, field, None)
    if isinstance(value, Money):
        return float(value.amount)
    return value


def hard_filter_passes(listing: Listing, filt: HardFilter) -> bool:
    value = _field_value(listing, filt.field)
    if value is None:
        return False
    return _OPERATORS[filt.operator](value, filt.value)


def apply_hard_filters(
    listings: Sequence[Listing], hard_filters: Sequence[HardFilter]
) -> list[Listing]:
    """ "Nothing over 80,000 km" removes rows; it does not merely penalise them
    (PHASE-5 SS4, gate 5.3). This is a distinct mechanism from `budget_fit`'s own hard-zero
    cliff: a generic stated constraint removes the row outright, so it can never resurface at
    any rank regardless of how well it scores on everything else.
    """
    if not hard_filters:
        return list(listings)
    return [
        listing for listing in listings if all(hard_filter_passes(listing, f) for f in hard_filters)
    ]


# -- per-criterion extraction (Listing + RequirementProfile -> primitives) --------------------


def _horizon_months(profile: RequirementProfile) -> int:
    if profile.horizon_months.is_filled and profile.horizon_months.value:
        return max(1, profile.horizon_months.value)
    return DEFAULT_HORIZON_MONTHS


def _resale_years(profile: RequirementProfile) -> int:
    months = _horizon_months(profile)
    return max(1, min(5, round(months / 12) or 1))


def _reference_price(listing: Listing, profile: RequirementProfile) -> Decimal:
    """What "price" means for scoring, not filtering: a rental total over the stated horizon
    for a rent goal, else the asking price (or `market_value` if the listing has none, e.g. a
    rent-only row surfaced under a `both`/unset goal).
    """
    if profile.goal.value is OfferType.RENT and listing.rental_rates is not None:
        return listing.rental_rates.monthly.amount * _horizon_months(profile)
    if listing.price_buy is not None:
        return listing.price_buy.amount
    return listing.market_value.amount


def _budget_fit(listing: Listing, profile: RequirementProfile) -> float:
    budget = profile.budget.value
    if budget is None:
        return 1.0  # nothing stated -- nothing to fail against
    price = _reference_price(listing, profile)
    return normalise_budget_fit(float(price), float(budget.amount))


def _resale_strength(listing: Listing, profile: RequirementProfile) -> float:
    years = _resale_years(profile)
    return normalise_resale_strength(listing.depreciation_curve[years - 1])


def _category_match(listing: Listing, profile: RequirementProfile) -> float:
    requested = [c.value for c in (profile.category.value or [])]
    return normalise_category_match(
        listing.category.value,
        requested,
        locked=profile.category.locked,
        confidence=profile.category.confidence,
    )


def _availability(listing: Listing, profile: RequirementProfile) -> float:
    target_date = profile.target_date.value
    if target_date is None:
        return 1.0  # no stated deadline -- nothing to be late against
    gap_days = (target_date - listing.available_from).days
    return normalise_availability(gap_days)


def score_listing(
    listing: Listing,
    profile: RequirementProfile,
    weights: WeightSet,
    *,
    running_cost_population: Sequence[float],
) -> ScoreBreakdown:
    normalised = {
        Criterion.BUDGET_FIT.value: _budget_fit(listing, profile),
        Criterion.RESALE_STRENGTH.value: _resale_strength(listing, profile),
        Criterion.CATEGORY_MATCH.value: _category_match(listing, profile),
        Criterion.AVAILABILITY.value: _availability(listing, profile),
        Criterion.RUNNING_COST.value: normalise_running_cost(
            float(monthly_running_cost(listing)), running_cost_population
        ),
    }
    return score_breakdown(weights, normalised)


# -- rationale + grounding (PHASE-5 SS6, CONSTITUTION II.3) -----------------------------------


def build_rationale(
    listing: Listing, breakdown: ScoreBreakdown, profile: RequirementProfile
) -> tuple[str, tuple[FieldRef, ...]]:
    """A deterministic, template-built rationale -- every number in it is one this function
    itself put there from a cited field, so it always validates. It is the code-side stand-in
    for what `prompts/explainer.md`'s live subagent narrates in prose from the same
    `ScoreBreakdown`; unlike the subagent, it has no room to invent a figure.
    """
    listing_key = f"{listing.source}:{listing.source_id}"
    price_field = "price_buy" if listing.price_buy is not None else "market_value"
    price = (listing.price_buy or listing.market_value).amount
    years = _resale_years(profile)
    retained_pct = round(listing.depreciation_curve[years - 1] * 100)
    top = max(breakdown.criteria, key=lambda c: c.contribution)

    sentences = [
        f"Holds {retained_pct}% of its value over the pricing horizon "
        f"(EUR {price:,.0f}), the largest single driver of its overall score "
        f"({_CRITERION_LABELS.get(top.criterion, top.criterion)})."
    ]
    citations = [
        FieldRef(listing_id=listing_key, field_name="depreciation_curve"),
        FieldRef(listing_id=listing_key, field_name=price_field),
    ]
    budget = profile.budget.value
    if budget is not None:
        within = "within" if price <= budget.amount else "over"
        sentences.append(f"Priced at EUR {price:,.0f}, {within} the stated budget.")
    sentences.append(f"{listing.mileage_km:,} km on the odometer.")
    citations.append(FieldRef(listing_id=listing_key, field_name="mileage_km"))
    return " ".join(sentences), tuple(citations)


def _derived_numbers(value: Any) -> set[float]:
    """Numbers derivable from one field's value: the raw figure, the same figure expressed as
    a percentage (a `depreciation_curve` fraction is *stated* as a percent in prose), and its
    rounding -- not a general theorem prover, just the handful of transforms
    `build_rationale` actually performs on a field before putting it in prose.
    """
    numbers: set[float] = set()

    def add(x: float) -> None:
        numbers.add(round(x, 2))
        numbers.add(round(x * 100, 2))
        numbers.add(round(x))

    if isinstance(value, Money):
        add(float(value.amount))
    elif isinstance(value, bool):
        pass
    elif isinstance(value, int | float | Decimal):
        add(float(value))
    elif isinstance(value, tuple | list):
        for item in value:
            numbers |= _derived_numbers(item)
    return numbers


def field_derived_numbers(listing: Listing, field_name: str) -> set[float]:
    return _derived_numbers(getattr(listing, field_name))


def _matches_any(n: float, available: set[float], *, tolerance: float = 0.5) -> bool:
    return any(abs(n - a) <= tolerance for a in available)


def validate_grounding(
    rationale: str, citations: Sequence[FieldRef], listings_by_key: Mapping[str, Listing]
) -> tuple[bool, tuple[float, ...]]:
    """CONSTITUTION II.3: every quantitative claim traces to a cited field. Returns whether
    the rationale is fully grounded, plus the specific numbers that weren't -- which is what
    lets gate 5.5 assert a *deliberately fabricated* statistic gets caught, not just that
    something failed.
    """
    claimed = extract_numbers(rationale)
    available: set[float] = set()
    for ref in citations:
        listing = listings_by_key.get(ref.listing_id)
        if listing is None:
            continue
        available |= field_derived_numbers(listing, ref.field_name)
    ungrounded = tuple(n for n in claimed if not _matches_any(n, available))
    return (not ungrounded, ungrounded)


def finalize_rationale(
    candidates: Sequence[tuple[str, tuple[FieldRef, ...]]],
    listings_by_key: Mapping[str, Listing],
) -> tuple[str, tuple[FieldRef, ...], bool]:
    """Up to two attempts against the grounding validator (PHASE-5 SS6's "two retries, then
    degrade" policy). The degraded form keeps the text but strips its citations and prefixes
    an `[unverified]` marker rather than showing an ungrounded claim as fact -- and rather
    than retrying forever.
    """
    last_text = ""
    for text, citations in candidates[:2]:
        ok, _ = validate_grounding(text, citations, listings_by_key)
        if ok:
            return text, citations, True
        last_text = text
    degraded = f"{UNVERIFIED_MARKER} {last_text}".strip()
    return degraded, (), False


# -- top-level ranking --------------------------------------------------------------------------


@dataclass(frozen=True)
class RankingResult:
    ranked: tuple[RankedResult, ...]
    weights: WeightSet


def rank(
    listings: Sequence[Listing],
    profile: RequirementProfile,
    *,
    weights: WeightSet | None = None,
) -> RankingResult:
    """Hard-filter, score, sort deterministically, then attach a grounded rationale to each
    survivor. `weights` defaults to `DEFAULT_WEIGHTS` -- in a live session the model supplies
    its own (CONSTITUTION II.2); `DEMO_MODE` and the gates use the fixed default.
    """
    weights = weights or DEFAULT_WEIGHTS
    survivors = apply_hard_filters(listings, profile.hard_filters)
    if not survivors:
        return RankingResult(ranked=(), weights=weights)

    population = [float(monthly_running_cost(listing)) for listing in survivors]
    scored = [
        (listing, score_listing(listing, profile, weights, running_cost_population=population))
        for listing in survivors
    ]
    scored.sort(key=lambda pair: ranking_sort_key(pair[1].total, pair[0].id))

    listings_by_key = {f"{listing.source}:{listing.source_id}": listing for listing in survivors}
    results = []
    for i, (listing, breakdown) in enumerate(scored, start=1):
        text, citations = build_rationale(listing, breakdown, profile)
        final_text, final_citations, _grounded = finalize_rationale(
            [(text, citations)], listings_by_key
        )
        results.append(
            RankedResult(
                listing_id=listing.id,
                rank=i,
                breakdown=breakdown,
                rationale=final_text,
                citations=final_citations,
            )
        )
    return RankingResult(ranked=tuple(results), weights=weights)


# -- critic pass (PHASE-5 SS8) -------------------------------------------------------------------


def _critic_violations(listing: Listing, profile: RequirementProfile) -> list[str]:
    problems: list[str] = []
    target_date = profile.target_date.value
    if target_date is not None and listing.available_from > target_date:
        problems.append(
            f"available_from {listing.available_from} is after target_date {target_date}"
        )
    budget = profile.budget.value
    if budget is not None and profile.goal.value is not OfferType.RENT:
        price = (listing.price_buy or listing.market_value).amount
        if price > budget.amount:
            problems.append(f"price {price} exceeds budget {budget.amount}")
    for hf in profile.hard_filters:
        if not hard_filter_passes(listing, hf):
            problems.append(f"{hf.field} fails {hf.operator} {hf.value}")
    return problems


def critic_pass(
    ranked: Sequence[RankedResult],
    listings_by_id: Mapping[uuid.UUID, Listing],
    profile: RequirementProfile,
) -> tuple[tuple[RankedResult, ...], tuple[str, ...]]:
    """A second, independent check of every candidate against every hard filter and the
    stated budget, reading the full listing rather than trusting the ranking pass
    (PHASE-5 SS8) -- the deterministic, gate-testable counterpart to what
    `prompts/critic.md`'s live subagent does by calling `get_listing` itself. Violators are
    dropped and the survivors renumbered, so no filtered listing reaches any rank
    (CONSTITUTION II.3 in spirit, gate 5.8).
    """
    survivors: list[RankedResult] = []
    violations: list[str] = []
    for result in ranked:
        listing = listings_by_id.get(result.listing_id)
        if listing is None:
            violations.append(f"{result.listing_id}: no listing found for critic re-check")
            continue
        problems = _critic_violations(listing, profile)
        if problems:
            violations.extend(f"{listing.source}:{listing.source_id}: {p}" for p in problems)
            continue
        survivors.append(result)
    renumbered = tuple(
        result.model_copy(update={"rank": i}) for i, result in enumerate(survivors, start=1)
    )
    return renumbered, tuple(violations)
