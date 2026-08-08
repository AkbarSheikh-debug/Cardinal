"""Exit gate for PHASE 10 -- TRUST.

    python -m scripts.gate_phase10

10.1/10.2/10.4 are pure/deterministic Python against `DEMO_MODE`'s real pipeline (D-015's
reasoning, already applied to gates 3/5/8/9): scoring, rationale-building, grounding and the
MCP tool layer none need a live model to prove an injected listing can't move them. 10.3 is a
static file scan, sharing its mechanism with gate 8.7 (`scripts/gate_common.py`) rather than
an independently-authored copy, so the two can't silently drift apart under the same
CONSTITUTION I.1 "enforced by" line.

10.5-10.9 are `[SCALE]` (PHASE-10 SS2) and report PENDING with a named reason each, the
convention gates 2.8/4.4-4.8/5.10/9.8-9.9 established -- CONSTITUTION III.3: ship every
`[MVP]` line, defer every `[SCALE]` one, never the reverse.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.gate_common import (
    DENYLIST_AUTHORING_FILES,
    DENYLIST_EXTRA_FILES,
    DENYLIST_SCAN_DIRS,
    PAYMENT_PROVIDER_TERMS,
    REPO_ROOT,
    Gate,
    Pending,
    scan_for_terms,
)

if TYPE_CHECKING:
    from src.domain.listing import Listing

CORPUS_PATH = REPO_ROOT / "tests" / "fixtures" / "security" / "injection_corpus.json"

#: PHASE-10 SS3's own six attack categories -- the corpus must cover all of them, not just
#: however many entries happen to add up to ~30.
EXPECTED_CATEGORIES = frozenset(
    {
        "instruction_override",
        "role_confusion",
        "delimiter_escape",
        "encoded_payloads",
        "tool_call_injection",
        "memory_poisoning",
    }
)

#: Endpoint-shaped BMW Group identifiers (CONSTITUTION I.3). Deliberately *not* the bare brand
#: word "BMW" -- that appears throughout `src/adapters/catalogue/taxonomy.py`'s legitimate
#: seeded brand pool (I.3's own carve-out: "brand names in our own generated dataset are
#: fine"), and a bare-word term would fail this gate against our own honest catalogue.
BMW_GROUP_ENDPOINT_TERMS: tuple[str, ...] = (
    "bmwgroup.com",
    "bmw-group.com",
    "api.bmw.com",
    "connecteddrive",
    "bmw-cardata",
    "mini.co.uk",
    "rolls-roycemotorcars.com",
)

#: A tool shaped like an episodic-memory write. None exist today (P4's `remember`/`recall`
#: tool is `[SCALE]`, PROGRESS.md's Phase 4 entry) -- this is what keeps that true on purpose
#: rather than by accident the next time a tool is added.
_MEMORY_WRITE_SHAPE = re.compile(
    r"remember|recall|memor|save_pref|store_fact|store_preference", re.IGNORECASE
)


def _load_corpus() -> list[dict[str, str]]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


async def _resolved_tool_names_everywhere() -> dict[str, tuple[str, ...]]:
    """Every tool name on every server, for both audiences -- gate 10.2's structural half.
    Reads the real SDK `Server.request_handlers`, the same mechanism gates 2.6/8.2 use, not
    this module's own bookkeeping.
    """
    from src.adapters.store import InMemoryListingStore
    from src.mcp.audience import resolved_tool_names
    from src.mcp.booking.server import build_booking_server
    from src.mcp.marketplace.server import build_marketplace_server
    from src.mcp.ui.server import build_ui_server

    store = InMemoryListingStore.seeded()
    found: dict[str, tuple[str, ...]] = {}
    for audience in ("model", "app"):
        configs = {
            "market": build_marketplace_server(store, audience=audience),
            "ui": build_ui_server(audience=audience),
            "booking": build_booking_server(audience=audience),
        }
        for server_name, config in configs.items():
            found[f"{server_name}:{audience}"] = await resolved_tool_names(config)
    return found


def build_gate() -> Gate:
    gate = Gate(10, "TRUST -- Injection defence, PII, tenancy, threat model")
    #: 10.1 builds the poisoned listings and the neutral profile once; 10.2 reuses the same
    #: corpus rather than reloading and re-deriving it.
    state: dict[str, Any] = {}

    # -- 10.1 [MVP] --------------------------------------------------------------------------
    @gate.criterion("10.1", "Injection corpus (~30 attempts): zero succeed")
    def _() -> str:
        from src.adapters.store import InMemoryListingStore
        from src.domain.costs import monthly_running_cost
        from src.domain.profile import RequirementProfile
        from src.domain.ranking import build_rationale, score_listing, validate_grounding
        from src.domain.scoring import DEFAULT_WEIGHTS
        from src.domain.trust import wrap_listing_content

        corpus = _load_corpus()
        state["corpus"] = corpus
        assert len(corpus) >= 30, f"corpus has only {len(corpus)} entries, need >=30"
        categories = {e["category"] for e in corpus}
        assert categories == EXPECTED_CATEGORIES, (
            f"corpus categories {sorted(categories)} != {sorted(EXPECTED_CATEGORIES)}"
        )

        store = InMemoryListingStore.seeded()
        base: Listing = store.listings[0]
        profile = RequirementProfile()
        population = [float(monthly_running_cost(base))]

        baseline_breakdown = score_listing(
            base, profile, DEFAULT_WEIGHTS, running_cost_population=population
        )
        baseline_rationale, baseline_citations = build_rationale(base, baseline_breakdown, profile)
        baseline_grounded, _ = validate_grounding(
            baseline_rationale, baseline_citations, {f"{base.source}:{base.source_id}": base}
        )
        assert baseline_grounded, "the baseline listing's own rationale failed to ground itself"

        failures: list[str] = []
        for entry in corpus:
            poisoned = base.model_copy(update={"description": entry["description"]})
            key = f"{poisoned.source}:{poisoned.source_id}"

            # Mechanism 2 (PHASE-10 SS3): ranking reads structured fields only. Swapping only
            # `description` must produce a byte-identical score -- rank manipulation via
            # listing text has literally nothing to act on.
            breakdown = score_listing(
                poisoned, profile, DEFAULT_WEIGHTS, running_cost_population=population
            )
            if breakdown != baseline_breakdown:
                failures.append(f"{entry['id']}: score changed by listing text alone")
                continue

            # Mechanism 3: a rationale built against the poisoned listing is exactly the one
            # built against the clean one (build_rationale never reads .description either)
            # and remains fully grounded.
            rationale, citations = build_rationale(poisoned, breakdown, profile)
            if rationale != baseline_rationale:
                failures.append(f"{entry['id']}: rationale text changed by listing text alone")
            grounded, ungrounded = validate_grounding(rationale, citations, {key: poisoned})
            if not grounded:
                failures.append(f"{entry['id']}: rationale ungrounded, numbers {ungrounded}")

            # Mechanism 1 + delimiter-escape category: wrapped, labelled, and escaped so no
            # payload can forge a second tag or break out of the label.
            wrapped = wrap_listing_content(poisoned)
            if 'trust="untrusted"' not in wrapped:
                failures.append(f"{entry['id']}: not labelled trust=untrusted")
            if wrapped.count("<listing_content ") != 1 or wrapped.count("</listing_content>") != 1:
                failures.append(f"{entry['id']}: forged an extra listing_content tag")
            if wrapped.count("<") != 2 or wrapped.count(">") != 2:
                failures.append(
                    f"{entry['id']}: {wrapped.count('<')} '<' / {wrapped.count('>')} '>' "
                    "in wrapped output, expected exactly 2 of each (one real tag pair)"
                )

        assert not failures, "injection(s) succeeded:\n  " + "\n  ".join(failures)
        by_category: dict[str, int] = {}
        for entry in corpus:
            by_category[entry["category"]] = by_category.get(entry["category"], 0) + 1
        return (
            f"{len(corpus)} attempts across {len(categories)} categories "
            f"({', '.join(f'{k}={v}' for k, v in sorted(by_category.items()))}), zero "
            "succeeded: identical score, identical rationale, single real wrapper tag, every "
            "time"
        )

    # -- 10.2 [MVP] --------------------------------------------------------------------------
    @gate.criterion("10.2", "Memory-poisoning attempt does not write to episodic memory")
    def _() -> str:
        from src.adapters.catalogue.generator import generate_catalogue
        from src.adapters.store import InMemoryListingStore
        from src.agent.demo import run_demo_session
        from src.agent.journal import session_uuid

        # Structural half: episodic memory (P4's `remember`/`recall` tool, PROGRESS.md Phase 4
        # SS[SCALE]) has zero write surface today -- no tool anywhere is even shaped like one,
        # on either audience, so there is no path an injection could reach regardless of what
        # a listing's text says.
        resolved = asyncio.run(_resolved_tool_names_everywhere())
        offending = {
            server: [name for name in names if _MEMORY_WRITE_SHAPE.search(name)]
            for server, names in resolved.items()
        }
        offending = {k: v for k, v in offending.items() if v}
        assert not offending, f"a memory-write-shaped tool exists: {offending}"

        # End-to-end half: seed five real memory-poisoning listings into the actual seeded
        # catalogue and run a full DEMO_MODE session against it -- the same utterance and
        # completion shape gate 9.1 already proved reaches TRANSACT -- then check nothing the
        # session persisted (profile, decision journal) carries the injected text.
        corpus: list[dict[str, str]] = state.get("corpus") or _load_corpus()
        poison_entries = [e for e in corpus if e["category"] == "memory_poisoning"]
        assert poison_entries, "no memory_poisoning entries in the corpus"

        listings = list(generate_catalogue())
        markers: list[str] = []
        for i, entry in enumerate(poison_entries):
            parts = entry["description"].split(". ", 1)
            markers.append(parts[1] if len(parts) > 1 else entry["description"])
            listings[i] = listings[i].model_copy(update={"description": entry["description"]})
        store = InMemoryListingStore(listings)

        async def run() -> Any:
            return await run_demo_session(
                ["I want to buy a sedan under 30000 euros by 2026-10-01"],
                store=store,
                session_id="gate102-memory-poisoning",
            )

        result = asyncio.run(run())
        assert result.state.booking_status == "draft_submitted", (
            f"poisoned-catalogue session did not complete normally: {result.state}"
        )

        journal_entries = asyncio.run(
            result.journal.for_session(session_uuid(result.state.session_id))
        )
        haystack = result.state.profile.model_dump_json() + " ".join(
            e.rationale + json.dumps(e.outcome, default=str) for e in journal_entries
        )
        leaked = [m for m in markers if m in haystack]
        assert not leaked, f"injected listing text leaked into profile or journal: {leaked}"

        return (
            f"0 memory-write-shaped tools across {len(resolved)} server x audience builds; "
            f"{len(poison_entries)} memory-poisoning listings seeded into a real catalogue, "
            f"session reached booking_status={result.state.booking_status!r}, zero leakage "
            "into the profile or the decision journal"
        )

    # -- 10.3 [MVP] --------------------------------------------------------------------------
    @gate.criterion("10.3", "Denylist scan: zero hits across source, deps, lockfiles")
    def _() -> str:
        terms = PAYMENT_PROVIDER_TERMS + BMW_GROUP_ENDPOINT_TERMS
        scanned, hits = scan_for_terms(
            terms,
            scan_dirs=DENYLIST_SCAN_DIRS,
            extra_files=DENYLIST_EXTRA_FILES,
            exclude_files=DENYLIST_AUTHORING_FILES,
        )
        assert not hits, "denylisted identifier(s) found:\n  " + "\n  ".join(hits)
        return (
            f"{scanned} files scanned across {DENYLIST_SCAN_DIRS + DENYLIST_EXTRA_FILES} for "
            f"{len(PAYMENT_PROVIDER_TERMS)} payment-provider (I.1) + "
            f"{len(BMW_GROUP_ENDPOINT_TERMS)} BMW Group endpoint (I.3) terms, 0 hits"
        )

    # -- 10.4 [MVP] --------------------------------------------------------------------------
    @gate.criterion("10.4", 'Listing text reaches the model wrapped and labelled trust="untrusted"')
    def _() -> str:
        from mcp import types as mcp_types
        from src.adapters.store import InMemoryListingStore
        from src.mcp.marketplace.server import build_marketplace_server

        store = InMemoryListingStore.seeded()
        config = build_marketplace_server(store, audience="model")
        server = config["instance"]
        handler = server.request_handlers[mcp_types.CallToolRequest]
        listing = store.listings[0]

        async def run() -> mcp_types.CallToolResult:
            request = mcp_types.CallToolRequest(
                params=mcp_types.CallToolRequestParams(
                    name="get_listing",
                    arguments={"source": listing.source, "source_id": listing.source_id},
                )
            )
            result = await handler(request)
            assert isinstance(result.root, mcp_types.CallToolResult)
            return result.root

        result = asyncio.run(run())
        assert not result.isError, f"get_listing returned an error: {result}"
        payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
        description = payload["description"]
        assert description.startswith("<listing_content "), description[:80]
        assert 'trust="untrusted"' in description, description[:120]
        assert f'listing_id="{listing.source_id}"' in description
        assert f'source="{listing.source}"' in description
        assert description.rstrip().endswith("</listing_content>")
        return (
            f"get_listing({listing.source}:{listing.source_id}).description arrives as "
            f'{description[:70]!r}... (full text wrapped, labelled trust="untrusted")'
        )

    # -- 10.5 [SCALE] ------------------------------------------------------------------------
    @gate.criterion("10.5", "[SCALE] PII scan over logs and a real span export: zero findings")
    def _() -> str:
        raise Pending(
            "the span-export half is already built and gated -- gate 9.6 asserts zero raw "
            "PII in a real OTel export via src/agent/tracing.py's RedactingSpanExporter "
            "(CONSTITUTION IV.1). What PHASE-10 SS4 adds on top -- a regex+entropy scan over "
            "log lines, and redaction for the memory tier -- is not built: there is no log "
            "sink yet to scan, and P4's episodic memory (what SS4 also names) is itself "
            "[SCALE] and unbuilt (PROGRESS.md Phase 4)."
        )

    # -- 10.6 [SCALE] ------------------------------------------------------------------------
    @gate.criterion(
        "10.6", "[SCALE] Two-tenant isolation test: zero cross-visibility in all stores"
    )
    def _() -> str:
        raise Pending(
            "multi-tenancy is not built -- no tenant_id column, no row-level security, no "
            "tenant-scoped query path anywhere in the schema (PHASE-10 SS5's own risk table: "
            "'tenant isolation added late is a schema migration'). This is a single-tenant "
            "system today by construction, not by an unenforced convention, so there is "
            "nothing yet for a cross-tenant-visibility test to exercise."
        )

    # -- 10.7 [SCALE] ------------------------------------------------------------------------
    @gate.criterion("10.7", "[SCALE] pip-audit + npm audit: no high/critical")
    def _() -> str:
        raise Pending(
            "neither scanner is wired into make verify or CI yet -- PHASE-10 SS7's supply-"
            "chain tier (pinned-hash verification, licence audit) is unbuilt."
        )

    # -- 10.8 [SCALE] ------------------------------------------------------------------------
    @gate.criterion("10.8", "[SCALE] Every 3D asset has an attribution entry")
    def _() -> str:
        raise Pending(
            "docs/ATTRIBUTION.md does not exist. Nothing to attribute yet either: the eight "
            "PowertrainExplainer GLBs (P6, DECISIONS.md D-028) are hand-built placeholder "
            "unit cubes, not licensed or third-party geometry -- the day real CC-BY models "
            "replace them is the day this file starts having entries to check."
        )

    # -- 10.9 [SCALE] ------------------------------------------------------------------------
    @gate.criterion("10.9", "[SCALE] docs/THREAT-MODEL.md exists with no open criticals")
    def _() -> str:
        raise Pending(
            "docs/THREAT-MODEL.md is not written yet. PHASE-10 SS8's five-adversary table "
            "(malicious seller, malicious user, compromised adapter, curious insider, model "
            "failure) is drafted in the plan doc itself but not promoted to a standalone, "
            "gated document."
        )

    return gate


def main(argv: list[str] | None = None) -> int:
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
