"""The ~30-entry prompt-injection corpus (CONSTITUTION I.4, PHASE-10 §3): CI-level coverage
over the same mechanisms `scripts/gate_phase10.py` proves as this phase's exit-gate evidence
(gates 10.1/10.2). Split out here rather than only living in the gate script because pytest's
parametrize gives one failure per corpus entry instead of one combined assertion list -- a
regression in, say, the `role_confusion` category alone shows up as five named failures, not
one line buried in a larger message.

Every check is structural: no live model is ever involved, matching D-015's reasoning for
gates 3/5/8/9. What's being proven is that ranking, rationale-building and the wrapper cannot
be moved by listing text no matter what that text says -- not that a model declined to obey it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.adapters.catalogue.generator import generate_catalogue
from src.adapters.store import InMemoryListingStore
from src.domain.costs import monthly_running_cost
from src.domain.listing import Listing
from src.domain.profile import RequirementProfile
from src.domain.ranking import build_rationale, score_listing, validate_grounding
from src.domain.scoring import DEFAULT_WEIGHTS
from src.domain.trust import wrap_listing_content

CORPUS_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "security" / "injection_corpus.json"
)
CORPUS: list[dict[str, str]] = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
CORPUS_IDS = [e["id"] for e in CORPUS]

EXPECTED_CATEGORIES = {
    "instruction_override",
    "role_confusion",
    "delimiter_escape",
    "encoded_payloads",
    "tool_call_injection",
    "memory_poisoning",
}

#: The three categories phrased plainly enough that `detect_injection`'s cheap classifier is
#: expected to catch every one -- confirmed by construction (tests/unit/test_domain_trust.py
#: covers the mechanism itself). `encoded_payloads` is deliberately excluded: evading a
#: keyword classifier via encoding is the whole point of that category, and nothing else in
#: this file depends on detection succeeding.
RELIABLY_FLAGGED_CATEGORIES = {"instruction_override", "role_confusion", "memory_poisoning"}

_MEMORY_WRITE_SHAPE = re.compile(
    r"remember|recall|memor|save_pref|store_fact|store_preference", re.IGNORECASE
)


def test_corpus_covers_every_phase_10_category_with_at_least_thirty_entries() -> None:
    assert len(CORPUS) >= 30, f"only {len(CORPUS)} entries, need >=30 (PHASE-10 §3)"
    assert {e["category"] for e in CORPUS} == EXPECTED_CATEGORIES


def test_corpus_ids_are_unique() -> None:
    assert len(set(CORPUS_IDS)) == len(CORPUS_IDS)


@pytest.fixture(scope="module")
def base_listing(store: InMemoryListingStore) -> Listing:
    return store.listings[0]


@pytest.fixture(scope="module")
def neutral_profile() -> RequirementProfile:
    return RequirementProfile()


@pytest.mark.parametrize("entry", CORPUS, ids=CORPUS_IDS)
def test_injected_description_cannot_move_the_score(
    entry: dict[str, str], base_listing: Listing, neutral_profile: RequirementProfile
) -> None:
    """Mechanism 2 (PHASE-10 §3): the scorer reads structured fields only. Swapping only
    `description` between an honest listing and an attack payload must not change a single
    number in the breakdown -- rank manipulation via listing text has nothing to act on.
    """
    poisoned = base_listing.model_copy(update={"description": entry["description"]})
    population = [float(monthly_running_cost(base_listing))]
    baseline = score_listing(
        base_listing, neutral_profile, DEFAULT_WEIGHTS, running_cost_population=population
    )
    scored = score_listing(
        poisoned, neutral_profile, DEFAULT_WEIGHTS, running_cost_population=population
    )
    assert scored == baseline


@pytest.mark.parametrize("entry", CORPUS, ids=CORPUS_IDS)
def test_injected_description_cannot_taint_the_rationale(
    entry: dict[str, str], base_listing: Listing, neutral_profile: RequirementProfile
) -> None:
    """Mechanism 3 (PHASE-10 §3, CONSTITUTION II.3): `build_rationale` never reads
    `description`, so the rationale it produces for a poisoned listing stays fully grounded --
    an injected claim has no `FieldRef` and cannot ride along inside a legitimate explanation.
    """
    poisoned = base_listing.model_copy(update={"description": entry["description"]})
    population = [float(monthly_running_cost(base_listing))]
    breakdown = score_listing(
        poisoned, neutral_profile, DEFAULT_WEIGHTS, running_cost_population=population
    )
    rationale, citations = build_rationale(poisoned, breakdown, neutral_profile)
    key = f"{poisoned.source}:{poisoned.source_id}"
    grounded, ungrounded = validate_grounding(rationale, citations, {key: poisoned})
    assert grounded, f"ungrounded numbers in rationale: {ungrounded}"


@pytest.mark.parametrize("entry", CORPUS, ids=CORPUS_IDS)
def test_wrapped_output_has_exactly_one_real_tag_pair(
    entry: dict[str, str], base_listing: Listing
) -> None:
    """Mechanism 1 + the delimiter-escape category (PHASE-10 §3, gate 10.4): labelled
    `trust="untrusted"`, and no payload -- however it tries to forge a closing tag or a second,
    differently-labelled block -- survives escaping as real markup.
    """
    poisoned = base_listing.model_copy(update={"description": entry["description"]})
    wrapped = wrap_listing_content(poisoned)
    assert 'trust="untrusted"' in wrapped
    assert wrapped.count("<listing_content ") == 1
    assert wrapped.count("</listing_content>") == 1
    assert wrapped.count("<") == 2, f"{entry['id']}: {wrapped!r}"
    assert wrapped.count(">") == 2, f"{entry['id']}: {wrapped!r}"


_reliable = [e for e in CORPUS if e["category"] in RELIABLY_FLAGGED_CATEGORIES]


@pytest.mark.parametrize("entry", _reliable, ids=[e["id"] for e in _reliable])
def test_the_cheap_classifier_catches_the_plainly_worded_categories(
    entry: dict[str, str], base_listing: Listing
) -> None:
    poisoned = base_listing.model_copy(update={"description": entry["description"]})
    wrapped = wrap_listing_content(poisoned)
    assert 'flagged="true"' in wrapped, (
        f"{entry['id']} ({entry['category']}) should have been flagged: {entry['description']!r}"
    )


# -- gate 10.2: memory poisoning -----------------------------------------------------------------


async def test_no_memory_shaped_tool_exists_on_any_server_or_audience(
    store: InMemoryListingStore,
) -> None:
    """P4's episodic `remember`/`recall` tool is `[SCALE]` and unbuilt (PROGRESS.md Phase 4) --
    this is what keeps that true on purpose, across every server and both audiences, rather
    than by accident the next time a tool is added.
    """
    from src.mcp.audience import resolved_tool_names
    from src.mcp.booking.server import build_booking_server
    from src.mcp.marketplace.server import build_marketplace_server
    from src.mcp.ui.server import build_ui_server

    offending: list[str] = []
    for audience in ("model", "app"):
        for config in (
            build_marketplace_server(store, audience=audience),
            build_ui_server(audience=audience),
            build_booking_server(audience=audience),
        ):
            names = await resolved_tool_names(config)
            offending.extend(n for n in names if _MEMORY_WRITE_SHAPE.search(n))
    assert not offending, f"a memory-write-shaped tool exists: {offending}"


async def test_memory_poisoning_listings_leave_no_trace_in_profile_or_journal() -> None:
    from src.agent.demo import run_demo_session
    from src.agent.journal import session_uuid

    poison_entries = [e for e in CORPUS if e["category"] == "memory_poisoning"]
    assert poison_entries

    listings = list(generate_catalogue())
    markers: list[str] = []
    for i, entry in enumerate(poison_entries):
        parts = entry["description"].split(". ", 1)
        markers.append(parts[1] if len(parts) > 1 else entry["description"])
        listings[i] = listings[i].model_copy(update={"description": entry["description"]})
    poisoned_store = InMemoryListingStore(listings)

    result = await run_demo_session(
        ["I want to buy a sedan under 30000 euros by 2026-10-01"],
        store=poisoned_store,
        session_id="test-memory-poisoning-corpus",
    )
    assert result.state.booking_status == "draft_submitted"

    journal_entries = await result.journal.for_session(session_uuid(result.state.session_id))
    haystack = result.state.profile.model_dump_json() + " ".join(
        e.rationale + json.dumps(e.outcome, default=str) for e in journal_entries
    )
    leaked = [m for m in markers if m in haystack]
    assert not leaked, f"injected listing text leaked into profile or journal: {leaked}"
