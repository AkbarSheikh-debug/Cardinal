"""Exit gate for PHASE 13 -- DEALER (PLAN-02 P13).

    python scripts/gate_phase13.py

Every criterion but 13.5 is pure Python against the generated catalogue -- no container, no
model, no API key (D-015's reasoning). 13.5 needs `web/node_modules` + Chromium and reports
PENDING without them, the convention gate 6.2 established.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from scripts.gate_common import REPO_ROOT, Gate, Pending, run_command
from src.adapters.catalogue.dealers import (
    DEALERS_PER_CITY,
    RealWorldCollisionError,
    assert_no_real_world_collisions,
    generate_dealers,
    real_world_denylist,
)
from src.adapters.catalogue.generator import SOURCES, generate_catalogue
from src.adapters.catalogue.taxonomy import CITIES
from src.adapters.dealer_store import InMemoryDealerDirectory
from src.adapters.filtering import matches
from src.domain.dealer import PayeeIdentity, VerificationStatus
from src.domain.enums import VehicleCondition
from src.domain.marketplace import SearchQuery

WEB = REPO_ROOT / "web"


def build_gate() -> Gate:
    gate = Gate(13, "DEALER -- directory, attribution, condition, payee identity")

    dealers = generate_dealers(42, SOURCES)
    catalogue = generate_catalogue()
    by_id = {d.id: d for d in dealers}

    # -- 13.1 [MVP] ---------------------------------------------------------------
    @gate.criterion("13.1", "every listing resolves to exactly one Dealer -- zero orphans")
    def _() -> str:
        orphans = [x for x in catalogue if x.dealer_id is None]
        assert not orphans, f"{len(orphans)} listings carry no dealer_id"
        dangling = [x for x in catalogue if x.dealer_id not in by_id]
        assert not dangling, f"{len(dangling)} listings point at an unknown dealer"

        mismatched = [
            x
            for x in catalogue
            if by_id[x.dealer_id].city != x.location.city or by_id[x.dealer_id].source != x.source
        ]
        assert not mismatched, (
            f"{len(mismatched)} listings sit with a dealer in another city or marketplace"
        )
        distinct = len({x.dealer_id for x in catalogue})
        return (
            f"{len(catalogue)}/{len(catalogue)} listings resolve to 1 dealer each across "
            f"{distinct} distinct dealers; 0 orphans, 0 dangling, 0 city/source mismatches"
        )

    # -- 13.2 [MVP] ---------------------------------------------------------------
    @gate.criterion("13.2", "two seed runs of the dealer generator are byte-identical")
    def _() -> str:
        import hashlib

        def digest(seed: int) -> str:
            payload = json.dumps(
                [d.model_dump(mode="json") for d in generate_dealers(seed, SOURCES)],
                sort_keys=True,
            )
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()

        first, second = digest(42), digest(42)
        assert first == second, f"two runs differed: {first[:16]} vs {second[:16]}"
        # A different seed must differ, or "deterministic" would be indistinguishable from
        # "hardcoded" -- the same guard gate 1.6's own reasoning implies.
        other = digest(7)
        assert other != first, "a different seed produced an identical directory"
        return (
            f"sha256 {first[:32]}... identical across two runs of {len(dealers)} dealers; "
            f"seed=7 differs ({other[:16]}...)"
        )

    # -- 13.3 [MVP] ---------------------------------------------------------------
    @gate.criterion("13.3", "no generated dealer name matches the real-brand/dealer denylist")
    def _() -> str:
        assert_no_real_world_collisions(dealers)
        # The check must be capable of firing, or it proves nothing (CONSTITUTION III.8's
        # "watch it fail" applied to a validator rather than a criterion).
        planted = dealers[0].model_copy(update={"display_name": "Toyota Motors Berlin"})
        try:
            assert_no_real_world_collisions((planted,))
        except RealWorldCollisionError:
            pass
        else:
            raise AssertionError("the collision check did not fire on a planted real brand")
        terms = real_world_denylist()
        return (
            f"{len(dealers)} dealer names scanned against {len(terms)} real-world terms "
            f"(every brand in the live taxonomy + {len(terms) - 24} known dealer groups), "
            f"0 hits; planted 'Toyota Motors Berlin' correctly rejected"
        )

    # -- 13.4 [MVP] ---------------------------------------------------------------
    @gate.criterion("13.4", "condition is a working filter: a new-only query returns zero used")
    def _() -> str:
        spread = Counter(x.condition for x in catalogue)
        for condition in VehicleCondition:
            assert spread[condition] > 0, f"no listing is {condition.value}"

        new_only = [
            x for x in catalogue if matches(x, SearchQuery(conditions=(VehicleCondition.NEW,)))
        ]
        assert new_only, "the new-only filter removed everything"
        assert all(x.condition is VehicleCondition.NEW for x in new_only)
        assert len(new_only) < len(catalogue), "the filter removed nothing"

        cpo = [
            x
            for x in catalogue
            if matches(x, SearchQuery(conditions=(VehicleCondition.CERTIFIED_PRE_OWNED,)))
        ]
        assert all(x.condition is VehicleCondition.CERTIFIED_PRE_OWNED for x in cpo)
        return (
            f"spread {dict(sorted((k.value, v) for k, v in spread.items()))}; "
            f"new-only returned {len(new_only)} rows, all new; cpo-only returned {len(cpo)}, "
            f"all certified_pre_owned"
        )

    # -- 13.5 [MVP] ---------------------------------------------------------------
    @gate.criterion("13.5", "dealer name, city, rating and verification render on a real CarCard")
    def _() -> str:
        npx = shutil.which("npx")
        installed = (WEB / "node_modules" / ".bin" / "playwright").exists() or (
            WEB / "node_modules" / ".bin" / "playwright.cmd"
        ).exists()
        if npx is None or not installed:
            raise Pending(
                "web/node_modules not installed -- run `npm install` and "
                "`npx playwright install chromium` inside web/, then re-run"
            )

        # Export a fresh fixture first: the spec renders real compiler output through the
        # real `MessageProcessor` and `carCatalog`, the same path gate 6.2 uses, so the
        # fixture has to carry this phase's new props rather than a stale copy.
        export = run_command([sys.executable, "-m", "scripts.export_ui_fixtures"], cwd=REPO_ROOT)
        assert export.returncode == 0, f"fixture export failed:\n{export.stderr[-1500:]}"

        result = run_command(
            [npx, "playwright", "test", "--config=playwright.dealer.config.ts"], cwd=WEB
        )
        assert result.returncode == 0, (
            f"playwright exited {result.returncode}\n{result.stdout[-2000:]}\n"
            f"{result.stderr[-800:]}"
        )
        report = WEB / "test-results" / "dealer.json"
        stats = {}
        if report.exists():
            stats = json.loads(report.read_text(encoding="utf-8")).get("stats", {})
        return (
            "web/tests/dealer-card.spec.ts rendered real compiler output through the real "
            f"carCatalog in Chromium -- stats="
            f"{ {k: stats.get(k) for k in ('expected', 'unexpected', 'flaky', 'skipped')} }"
        )

    # -- 13.6 [MVP] ---------------------------------------------------------------
    @gate.criterion("13.6", "the directory covers every city on every marketplace")
    def _() -> str:
        expected = len(SOURCES) * len(CITIES) * DEALERS_PER_CITY
        assert len(dealers) == expected, f"expected {expected} dealers, got {len(dealers)}"
        assert len({d.id for d in dealers}) == len(dealers), "duplicate dealer ids"

        spread = Counter(d.verification_status for d in dealers)
        for status in VerificationStatus:
            assert spread[status] > 0, (
                f"no dealer is {status.value} -- P14's payee flag would never be exercised"
            )
        stocked = len({x.dealer_id for x in catalogue})
        return (
            f"{len(dealers)} dealers = {len(SOURCES)} sources x {len(CITIES)} cities x "
            f"{DEALERS_PER_CITY}; verification spread "
            f"{dict(sorted((k.value, v) for k, v in spread.items()))}; {stocked} hold stock"
        )

    # -- 13.7 [MVP] ---------------------------------------------------------------
    @gate.criterion("13.7", "PayeeIdentity for an unverified dealer reports it, never blank")
    def _() -> str:
        directory = InMemoryDealerDirectory.seeded()
        unverified = next(
            d for d in dealers if d.verification_status is VerificationStatus.UNVERIFIED
        )
        pending = next(d for d in dealers if d.verification_status is VerificationStatus.PENDING)
        verified = next(d for d in dealers if d.verification_status is VerificationStatus.VERIFIED)

        for dealer, expect_flag in ((unverified, True), (pending, True), (verified, False)):
            payee = PayeeIdentity.of(dealer)
            assert payee.needs_flag is expect_flag, (
                f"{dealer.verification_status.value} produced needs_flag={payee.needs_flag}"
            )
            assert payee.legal_name and payee.address and payee.phone, (
                "a payee disclosure came back with a blank field"
            )

        # A listing that predates the re-seed resolves to None rather than raising -- a
        # checkout must not 500 because a row has no dealer yet.
        import anyio

        assert anyio.run(lambda: directory.payee(None)) is None
        return (
            f"unverified={unverified.display_name!r} -> flagged; "
            f"pending={pending.display_name!r} -> flagged; "
            f"verified={verified.display_name!r} -> not flagged; payee(None) -> None"
        )

    # -- 13.8 [MVP] ---------------------------------------------------------------
    @gate.criterion("13.8", "gate 1 still green -- catalogue counts and correlations unchanged")
    def _() -> str:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.gate_phase1"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, (
            "gate 1 went red after P13 touched the generator:\n" + result.stdout[-2500:]
        )
        tail = [line.strip() for line in result.stdout.splitlines() if "passed" in line]
        return f"scripts.gate_phase1 exits 0 -- {tail[-1] if tail else 'green'}"

    return gate


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
