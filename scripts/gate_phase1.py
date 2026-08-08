"""Exit gate for PHASE 1 -- Inventory.

Every criterion **prints its counts**. PHASE-1 §7: never eyeball these.

    python scripts/gate_phase1.py                  # 1.10 is PENDING with no stack running
    python scripts/gate_phase1.py --require-stack  # 1.10 must genuinely pass
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics as st
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.gate_common import REPO_ROOT, Gate, Pending, python_executable, run_command
from src.adapters.catalogue.generator import (
    MIN_BRANDS_PER_CATEGORY,
    PRICE_NOISE_SIGMA,
    expected_market_value_eur,
    generate_catalogue,
)
from src.adapters.catalogue.taxonomy import brand_tier
from src.adapters.registry import registered_adapters, registered_source_names
from src.adapters.store import InMemoryListingStore
from src.domain.enums import VehicleCategory
from src.domain.listing import Listing, ListingSummary
from src.domain.marketplace import MAX_SUMMARY_TOKENS, summary_token_estimate

MAX_PRICE_Z = 2.0
DEFAULT_HEALTH_URL = "http://localhost:8000/health"

CATALOGUE: tuple[Listing, ...] = generate_catalogue()


def build_gate(*, require_stack: bool, health_url: str) -> Gate:
    gate = Gate(1, "Inventory -- adapter protocol, seeded catalogue, structured search")

    # -- 1.1 -----------------------------------------------------------------
    @gate.criterion("1.1", ">=100 listings (target 240)")
    def _() -> str:
        total = len(CATALOGUE)
        assert total >= 100, f"only {total} listings"
        return f"{total} listings generated"

    # -- 1.2 -----------------------------------------------------------------
    @gate.criterion("1.2", ">=10 distinct categories (target 12)")
    def _() -> str:
        categories = sorted({item.category.value for item in CATALOGUE})
        assert len(categories) >= 10, f"only {len(categories)}: {categories}"
        return f"{len(categories)} categories: {', '.join(categories)}"

    # -- 1.3 -----------------------------------------------------------------
    @gate.criterion("1.3", ">=10 distinct brands within EVERY category")
    def _() -> str:
        by_category: defaultdict[VehicleCategory, set[str]] = defaultdict(set)
        for item in CATALOGUE:
            by_category[item.category].add(item.brand)

        lines = []
        thin = []
        for category in sorted(by_category, key=lambda c: c.value):
            brands = by_category[category]
            marker = "ok " if len(brands) >= MIN_BRANDS_PER_CATEGORY else "LOW"
            lines.append(f"{marker} {category.value:<12} {len(brands):>2} brands")
            if len(brands) < MIN_BRANDS_PER_CATEGORY:
                thin.append(category.value)
        assert not thin, f"below the floor of {MIN_BRANDS_PER_CATEGORY}: {thin}"
        return "\n".join(lines)

    # -- 1.4 -----------------------------------------------------------------
    @gate.criterion("1.4", "both rent and buy present, each >=40")
    def _() -> str:
        mix = Counter(item.offer_type.value for item in CATALOGUE)
        buyable = sum(1 for i in CATALOGUE if i.offer_type.is_buyable)
        rentable = sum(1 for i in CATALOGUE if i.offer_type.is_rentable)
        assert buyable >= 40, f"only {buyable} buyable"
        assert rentable >= 40, f"only {rentable} rentable"
        return (
            f"buyable={buyable} rentable={rentable} "
            f"(buy={mix['buy']} rent={mix['rent']} both={mix['both']})"
        )

    # -- 1.5 -----------------------------------------------------------------
    @gate.criterion("1.5", "adapter contract suite passes against every adapter")
    def _() -> str:
        proc = run_command(
            [python_executable(), "-m", "pytest", "tests/contract", "-q", "--no-header"]
        )
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-200:]
        assert proc.returncode == 0, f"contract suite red: {tail}"
        adapters = ", ".join(a.name for a in registered_adapters(InMemoryListingStore(())))
        return f"{tail}\nparametrised over: {adapters}"

    # -- 1.6 -----------------------------------------------------------------
    @gate.criterion("1.6", "two seed runs with the same seed are byte-identical")
    def _() -> str:
        """Two *processes*, not two calls.

        Calling the generator twice in one interpreter would miss exactly the bugs this
        criterion exists to catch -- hash randomisation and any module-level state that
        survives within a process but differs between them.
        """
        digests = []
        with TemporaryDirectory() as tmp:
            for run in (1, 2):
                out = Path(tmp) / f"run{run}.json"
                proc = run_command(
                    [python_executable(), "-m", "scripts.seed_marketplace", "--dump", str(out)]
                )
                assert proc.returncode == 0, f"seed run {run} failed: {proc.stderr[-300:]}"
                digests.append(hashlib.sha256(out.read_bytes()).hexdigest())
        assert digests[0] == digests[1], f"seed is not deterministic: {digests}"
        return f"sha256 {digests[0][:32]}... identical across two processes"

    # -- 1.7 -----------------------------------------------------------------
    @gate.criterion("1.7", "every Listing validates; raw non-empty on all rows")
    def _() -> str:
        empty_raw = [i.source_id for i in CATALOGUE if not i.raw]
        assert not empty_raw, f"{len(empty_raw)} rows lost their upstream payload"
        for item in CATALOGUE:
            restored = Listing.model_validate(item.model_dump(mode="json"))
            assert restored == item, f"{item.source_id} did not survive a round trip"
        return f"{len(CATALOGUE)}/{len(CATALOGUE)} rows validate and round-trip; raw non-empty"

    # -- 1.8 -----------------------------------------------------------------
    @gate.criterion("1.8", "price/mileage/year correlation holds (no listing >2 sigma)")
    def _() -> str:
        """The one people skip. Skip it and every ranking screenshot looks wrong."""
        actual, expected, worst = [], [], (0.0, "")
        for item in CATALOGUE:
            model = expected_market_value_eur(
                item.category, brand_tier(item.brand), item.year, item.mileage_km
            )
            price = float(item.market_value.amount)
            actual.append(price)
            expected.append(model)
            z = abs(price / model - 1.0) / PRICE_NOISE_SIGMA
            if z > worst[0]:
                worst = (z, f"{item.source_id} {item.year} {item.brand} {item.model}")

        correlation = st.correlation(actual, expected)
        assert worst[0] <= MAX_PRICE_Z, f"{worst[1]} is {worst[0]:.2f} sigma off its cohort"
        assert correlation >= 0.95, f"price barely tracks the model (r={correlation:.4f})"
        return (
            f"max |z| = {worst[0]:.3f} (limit {MAX_PRICE_Z}) on {worst[1]}\n"
            f"pearson r(actual, model) = {correlation:.4f} across {len(CATALOGUE)} rows"
        )

    # -- 1.9 -----------------------------------------------------------------
    @gate.criterion("1.9", "search returns summaries only, <=200 tokens each")
    def _() -> str:
        sizes = [summary_token_estimate(ListingSummary.from_listing(i)) for i in CATALOGUE]
        biggest = max(sizes)
        assert biggest <= MAX_SUMMARY_TOKENS, f"largest summary is {biggest} tokens"
        full = max(len(json.dumps(i.model_dump(mode="json"))) // 4 for i in CATALOGUE)
        return (
            f"max summary {biggest} tokens, mean {st.fmean(sizes):.1f} "
            f"(cap {MAX_SUMMARY_TOKENS}); a full record would be ~{full} tokens"
        )

    # -- 1.10 ----------------------------------------------------------------
    @gate.criterion("1.10", "docker compose up -> /health 200 with a listing count")
    def _() -> str:
        try:
            with urllib.request.urlopen(health_url, timeout=5) as response:
                code = response.status
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            if require_stack:
                raise AssertionError(f"{health_url} unreachable: {exc}") from exc
            raise Pending(
                f"{health_url} unreachable -- start the stack with `docker compose up`, "
                "then re-run with --require-stack"
            ) from exc

        assert code == 200, f"/health returned {code}"
        assert payload.get("status") == "ok", f"/health says {payload.get('status')!r}"
        count = payload.get("listings")
        assert isinstance(count, int) and count >= 100, f"/health reports {count} listings"
        per_source = payload.get("sources", {})
        for name in registered_source_names():
            assert per_source.get(name, 0) > 0, f"{name} has no listings behind /health"
        return (
            f"200 OK from {health_url}\n"
            f"backend={payload.get('backend')} listings={count} sources={per_source}"
        )

    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-stack",
        action="store_true",
        help="fail criterion 1.10 instead of reporting it PENDING when /health is unreachable",
    )
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    args = parser.parse_args(argv)

    return build_gate(require_stack=args.require_stack, health_url=args.health_url).run()


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    sys.exit(main())
