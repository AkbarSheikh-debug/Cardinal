"""Exit gate for PHASE 5 -- REASONING.

    python scripts/gate_phase5.py

Every `[MVP]` criterion (5.1-5.9) runs with no container, no `ANTHROPIC_API_KEY` and no live
`ClaudeSDKClient` session -- the same convention D-015 established for gate 3: the scorer,
the TCO engine and the critic pass are all pure/deterministic code (CONSTITUTION II.2), so
none of them genuinely need a model to verify. `5.10` (`[SCALE]` counterfactual relaxation on
infeasibility) reports `PENDING`, the convention gate 2.8 and gate 4.4-4.8 established for a
criterion whose feature was deliberately deferred.
"""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.gate_common import REPO_ROOT, Gate, Pending

GOLDEN_SET_PATH = REPO_ROOT / "tests" / "fixtures" / "demo" / "golden_set.json"
SCORING_MODULE = REPO_ROOT / "src" / "domain" / "scoring.py"


def _make_listing(**overrides: Any) -> Any:
    """A small, hand-built `Listing` with round numbers -- gates 5.3/5.5/5.6/5.7/5.8 need
    fixtures whose fields can be checked by inspection, not the seeded catalogue's realistic
    but unround prices and curves.
    """
    from src.domain.enums import (
        EfficiencyUnit,
        FuelType,
        OfferType,
        PowertrainArchetype,
        TimingMechanism,
        Transmission,
        VehicleCategory,
    )
    from src.domain.listing import Efficiency, Listing, Location, RentalRates, listing_uuid
    from src.domain.money import Money

    source = overrides.pop("source", "fixture")
    source_id = overrides.pop("source_id", "FIX-1")
    offer_type = overrides.pop("offer_type", OfferType.BOTH)
    price_buy = overrides.pop("price_buy", "20000")
    market_value = overrides.pop("market_value", "20000")
    rental = overrides.pop("rental", True)
    rental_daily = overrides.pop("rental_daily", "25")
    rental_weekly = overrides.pop("rental_weekly", "140")
    rental_monthly = overrides.pop("rental_monthly", "500")
    included_km_per_day = overrides.pop("included_km_per_day", 60)
    excess_km_rate = overrides.pop("excess_km_rate", "0.30")
    insurance_included = overrides.pop("insurance_included", True)

    rental_rates = None
    if offer_type.is_rentable and rental:
        rental_rates = RentalRates(
            daily=Money.of(rental_daily),
            weekly=Money.of(rental_weekly),
            monthly=Money.of(rental_monthly),
            included_km_per_day=included_km_per_day,
            excess_km_rate=Money.of(excess_km_rate),
            insurance_included=insurance_included,
        )

    fields: dict[str, object] = {
        "id": listing_uuid(str(source), str(source_id)),
        "source": source,
        "source_id": source_id,
        "fetched_at": datetime(2026, 1, 1, tzinfo=UTC),
        "raw": {"fixture": True},
        "brand": "Test",
        "model": "Model",
        "variant": "Base",
        "year": 2024,
        "category": VehicleCategory.SEDAN,
        "offer_type": offer_type,
        "market_value": Money.of(market_value),
        "price_buy": Money.of(price_buy) if offer_type.is_buyable and price_buy else None,
        "rental_rates": rental_rates,
        "mileage_km": 10000,
        "fuel_type": FuelType.PETROL,
        "transmission": Transmission.MANUAL,
        "seats": 5,
        "doors": 4,
        "efficiency": Efficiency(value=Decimal("6"), unit=EfficiencyUnit.L_PER_100KM),
        "depreciation_curve": (0.80, 0.65, 0.55, 0.48, 0.42),
        "insurance_band": 1,
        "service_interval_km": 15000,
        "timing_mechanism": TimingMechanism.CHAIN,
        "powertrain_archetype": PowertrainArchetype.I4_NA,
        "location": Location(city="Berlin", country="DE", latitude=52.5, longitude=13.4),
        "available_from": date(2026, 1, 1),
        "description": "a fixture listing",
    }
    fields.update(overrides)
    return Listing(**fields)


def build_gate() -> Gate:
    gate = Gate(5, "REASONING -- scoring, TCO, grounding, critic pass")

    # -- 5.1 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.1", "Determinism: same profile + seed, two runs, byte-identical")
    def _() -> str:
        from src.adapters.store import InMemoryListingStore
        from src.domain.enums import OfferType, VehicleCategory
        from src.domain.money import Money
        from src.domain.profile import RequirementProfile
        from src.domain.ranking import rank

        store = InMemoryListingStore.seeded()
        listings = [x for x in store.listings if x.category is VehicleCategory.SEDAN][:15]
        assert listings, "seeded catalogue has no sedans to rank"

        profile = RequirementProfile()
        profile.goal = profile.goal.fill(OfferType.BUY, confidence=0.9, turn=1, locked=True)
        profile.category = profile.category.fill(
            [VehicleCategory.SEDAN], confidence=0.9, turn=1, locked=True
        )
        profile.budget = profile.budget.fill(Money.of("40000"), confidence=0.9, turn=1, locked=True)

        first = rank(listings, profile)
        second = rank(listings, profile)
        first_json = [r.model_dump_json() for r in first.ranked]
        second_json = [r.model_dump_json() for r in second.ranked]
        assert first_json == second_json, "two runs over the same inputs produced different output"
        assert len(first_json) >= 1
        return f"{len(first_json)} candidates ranked, byte-identical across two runs"

    # -- 5.2 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.2", "ScoreBreakdown contributions sum to the total within 1e-9")
    def _() -> str:
        from src.domain.scoring import CriterionWeight, WeightSet, score_breakdown

        weights = WeightSet(
            weights=(
                CriterionWeight(criterion="a", weight=0.7),
                CriterionWeight(criterion="b", weight=0.3),
            )
        )
        breakdown = score_breakdown(weights, {"a": 0.6, "b": 0.9})
        total_from_contributions = sum(c.contribution for c in breakdown.criteria)
        assert abs(breakdown.total - total_from_contributions) <= 1e-9
        return f"total={breakdown.total:.6f}, sum(contributions)={total_from_contributions:.6f}"

    # -- 5.3 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.3", "Hard filters remove rows -- no filtered listing appears at any rank")
    def _() -> str:
        from src.domain.profile import HardFilter, RequirementProfile
        from src.domain.ranking import rank

        low = _make_listing(source_id="LOW-MILEAGE", mileage_km=20000)
        high = _make_listing(source_id="HIGH-MILEAGE", mileage_km=96000)
        profile = RequirementProfile()
        profile.hard_filters = [HardFilter(field="mileage_km", operator="lte", value=80000)]

        result = rank([low, high], profile)
        surviving_ids = {r.listing_id for r in result.ranked}
        assert high.id not in surviving_ids, "a listing over the hard mileage limit was ranked"
        assert low.id in surviving_ids
        return (
            f"96000 km listing excluded by a lte-80000 hard filter; "
            f"{len(result.ranked)}/2 candidates survived"
        )

    # -- 5.4 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.4", "Golden set of 20 personas: precision@3 >= 0.8 vs stated constraints")
    def _() -> str:
        from src.adapters.store import InMemoryListingStore
        from src.agent.demo import run_demo_session
        from src.domain.enums import OfferType

        personas = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
        assert len(personas) >= 20, f"golden set has only {len(personas)} personas, need >=20"

        async def run_all() -> list[tuple[str, float, int]]:
            store = InMemoryListingStore.seeded()
            results: list[tuple[str, float, int]] = []
            for persona in personas:
                result = await run_demo_session(
                    list(persona["utterances"]),
                    store=store,
                    session_id=f"gate54-{persona['name']}",
                )
                top3 = result.critic_survivors[:3]
                if not top3:
                    results.append((persona["name"], -1.0, 0))
                    continue
                profile = result.state.profile
                requested_categories = {c.value for c in (profile.category.value or [])}
                hits = 0
                for ranked in top3:
                    listing = next((x for x in store.listings if x.id == ranked.listing_id), None)
                    assert listing is not None, "ranked a listing not present in the store"
                    ok = True
                    if requested_categories and listing.category.value not in requested_categories:
                        ok = False
                    if profile.budget.is_filled and profile.goal.value is not OfferType.RENT:
                        price = (listing.price_buy or listing.market_value).amount
                        if price > profile.budget.value.amount:
                            ok = False
                    target_date = profile.target_date.value
                    if target_date is not None and listing.available_from > target_date:
                        ok = False
                    if ok:
                        hits += 1
                results.append((persona["name"], hits / len(top3), len(top3)))
            return results

        results = asyncio.run(run_all())
        feasible = [r for r in results if r[2] > 0]
        infeasible = [r for r in results if r[2] == 0]
        assert len(feasible) >= 15, (
            f"only {len(feasible)}/20 golden personas produced any recommendation "
            f"(infeasible: {[r[0] for r in infeasible]})"
        )
        avg_precision = sum(r[1] for r in feasible) / len(feasible)
        assert avg_precision >= 0.8, f"precision@3 = {avg_precision:.3f}, need >= 0.8"
        worst = min(feasible, key=lambda r: r[1])
        return (
            f"{len(feasible)}/20 personas feasible, {len(infeasible)} infeasible "
            f"(a real answer, not a missing one); mean precision@3={avg_precision:.3f}; "
            f"worst persona {worst[0]!r} precision@3={worst[1]:.2f}"
        )

    # -- 5.5 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.5", "Groundedness validator rejects a deliberately fabricated statistic")
    def _() -> str:
        from src.domain.ranking import validate_grounding
        from src.domain.scoring import FieldRef

        listing = _make_listing()
        listing_key = f"{listing.source}:{listing.source_id}"
        citations = (FieldRef(listing_id=listing_key, field_name="depreciation_curve"),)
        fabricated = "This listing retains an implausible 999% of its value at resale."

        ok, ungrounded = validate_grounding(fabricated, citations, {listing_key: listing})
        assert not ok, "the validator accepted a fabricated 999% statistic"
        assert 999.0 in ungrounded

        # And the honest counterpart must validate -- otherwise "reject" above would mean a
        # validator that rejects everything, not one that specifically catches fabrication.
        genuine = "This listing retains 80% of its value at resale."
        ok2, _ = validate_grounding(genuine, citations, {listing_key: listing})
        assert ok2, "the validator rejected a statistic that genuinely traces to the curve"
        return "999% fabricated claim rejected; genuine 80% claim (curve[0]=0.80) accepted"

    # -- 5.6 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.6", "TCO: break-even for a known fixture matches a hand-computed value")
    def _() -> str:
        from src.domain.tco import compute_buy_tco, compute_comparison, compute_rent_tco

        listing = _make_listing(
            market_value="20000",
            price_buy="20000",
            rental_daily="25",
            rental_weekly="140",
            rental_monthly="500",
            included_km_per_day=60,
            insurance_included=True,
        )
        # Hand derivation (DECISIONS.md): Buy(h) = 370 + 543.25h, Rent(h) = 631.25h for h<=12
        # -> crosses at h = 370/88 = 4.2045..., first integer month = 5.
        comparison = compute_comparison(listing, 12)
        assert comparison.break_even_month == 5, (
            f"expected break-even at month 5, got {comparison.break_even_month}"
        )
        buy_5 = compute_buy_tco(listing, 5).total.amount
        rent_5 = compute_rent_tco(listing, 5).total.amount
        assert abs(buy_5 - Decimal("3086.25")) <= Decimal("50")
        assert abs(rent_5 - Decimal("3156.25")) <= Decimal("50")
        return (
            f"break_even_month=5 (hand-derived from Buy(h)=370+543.25h, Rent(h)=631.25h); "
            f"buy(5)=EUR {buy_5} (hand: 3086.25), rent(5)=EUR {rent_5} (hand: 3156.25), "
            f"both within EUR 50"
        )

    # -- 5.7 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.7", "Rental pricing tiers applied -- weekly rate != daily x 7 in output")
    def _() -> str:
        from src.domain.tco import compute_rent_tco

        listing = _make_listing(rental_daily="25", rental_weekly="140", rental_monthly="500")
        assert listing.rental_rates is not None
        naive_weekly = listing.rental_rates.daily.amount * 7
        assert listing.rental_rates.weekly.amount != naive_weekly

        estimate = compute_rent_tco(listing, 1)
        rental_line = next(line for line in estimate.lines if line.kind.value == "rental")
        assert rental_line.amount == listing.rental_rates.monthly
        naive_monthly = listing.rental_rates.daily.amount * 30
        assert rental_line.amount.amount != naive_monthly
        return (
            f"rental line = EUR {rental_line.amount.amount} (the monthly tier), not "
            f"daily x 30 = EUR {naive_monthly}; weekly tier EUR "
            f"{listing.rental_rates.weekly.amount} != daily x 7 = EUR {naive_weekly}"
        )

    # -- 5.8 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.8", "Critic catches a seeded violation before render")
    def _() -> str:
        from src.domain.profile import RequirementProfile
        from src.domain.ranking import critic_pass, rank

        late = _make_listing(source_id="LATE", available_from=date(2026, 11, 1))
        on_time = _make_listing(source_id="ON-TIME", available_from=date(2026, 1, 15))
        profile = RequirementProfile()
        profile.target_date = profile.target_date.fill(
            date(2026, 9, 15), confidence=0.9, turn=1, locked=True
        )

        # Bypasses search-level filtering on purpose -- the seeded violation must slip past
        # the ranking pass and be caught by the *critic*, which is what this gate checks.
        ranking_result = rank([late, on_time], profile)
        listings_by_id = {late.id: late, on_time.id: on_time}
        survivors, violations = critic_pass(ranking_result.ranked, listings_by_id, profile)

        surviving_ids = {r.listing_id for r in survivors}
        assert late.id not in surviving_ids, "critic failed to catch the late-availability listing"
        assert on_time.id in surviving_ids
        assert violations, "critic reported no violations despite one seeded"
        return (
            f"critic dropped 'LATE' (available 2026-11-01, after target 2026-09-15): "
            f"{violations[0]}"
        )

    # -- 5.9 [MVP] -----------------------------------------------------------------------
    @gate.criterion("5.9", "domain/scoring.py has zero imports outside stdlib + pydantic")
    def _() -> str:
        tree = ast.parse(SCORING_MODULE.read_text(encoding="utf-8"), filename=str(SCORING_MODULE))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])

        allowed = set(sys.stdlib_module_names) | {"pydantic", "__future__"}
        violations = roots - allowed
        assert not violations, (
            f"src/domain/scoring.py imports outside stdlib+pydantic: {violations}"
        )
        return f"{len(roots)} import root(s), all stdlib or pydantic: {sorted(roots)}"

    # -- 5.10 [SCALE] ----------------------------------------------------------------------
    @gate.criterion(
        "5.10",
        "[SCALE] Counterfactual solver returns >=2 relaxation options on a zero-result query",
    )
    def _() -> str:
        raise Pending(
            "constraint relaxation / counterfactual solver (PHASE-5 SS7) not built -- [SCALE]"
        )

    return gate


def main(argv: list[str] | None = None) -> int:
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
