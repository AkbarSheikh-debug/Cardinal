"""The `PreToolUse` audit hook and the `can_use_tool` search gate (PHASE-3 §6, gate 3.6,
gate 3.8's underlying mechanism).
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from claude_agent_sdk import ToolPermissionContext

from src.agent.guardrails import (
    MIN_SLOTS_BEFORE_SEARCH,
    AuditLog,
    build_audit_hook,
    build_search_gate,
    extract_candidate_ids,
    hash_args,
)
from src.agent.phase_machine import SessionState, new_session
from src.domain.enums import OfferType, VehicleCategory
from src.domain.money import Money


def _profile_with_n_required_slots_filled(n: int) -> SessionState:
    state = new_session("s1")
    profile = state.profile
    if n >= 1:
        profile.goal = profile.goal.fill(OfferType.BUY, confidence=0.9, turn=1, locked=True)
    if n >= 2:
        profile.category = profile.category.fill(
            [VehicleCategory.SUV], confidence=0.9, turn=1, locked=True
        )
    if n >= 3:
        profile.budget = profile.budget.fill(Money.of("20000"), confidence=0.9, turn=1, locked=True)
    if n >= 4:
        profile.target_date = profile.target_date.fill(
            date(2026, 9, 1), confidence=0.9, turn=1, locked=True
        )
    return state.model_copy(update={"profile": profile})


def _hook_input(
    session_id: str, tool_name: str, tool_input: dict[str, object]
) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "transcript_path": "",
        "cwd": "",
        "tool_use_id": "call-1",
    }


def test_hash_args_is_stable_regardless_of_key_order() -> None:
    a = hash_args({"x": 1, "y": 2})
    b = hash_args({"y": 2, "x": 1})
    assert a == b


def test_hash_args_differs_for_different_args() -> None:
    assert hash_args({"x": 1}) != hash_args({"x": 2})


async def test_audit_hook_records_every_tool_call() -> None:
    log = AuditLog()
    state = _profile_with_n_required_slots_filled(4)
    hook = build_audit_hook(log, "s1", lambda sid: state if sid == "s1" else None)

    await hook(_hook_input("s1", "get_listing", {"source_id": "AB-1"}), None, {"signal": None})
    await hook(_hook_input("s1", "get_quote", {"source_id": "AB-1"}), None, {"signal": None})

    entries = log.for_session("s1")
    assert len(entries) == 2
    assert {e.tool_name for e in entries} == {"get_listing", "get_quote"}
    assert all(e.session_id == "s1" for e in entries)


async def test_audit_hook_denies_search_with_no_profile_started() -> None:
    log = AuditLog()
    hook = build_audit_hook(log, "s1", lambda sid: None)
    result = await hook(_hook_input("s1", "search_cars", {}), None, {"signal": None})
    output = result.get("hookSpecificOutput", {})
    assert output.get("permissionDecision") == "deny"
    # It still logs the attempt -- denial is not exemption from the audit trail.
    assert len(log.for_session("s1")) == 1


async def test_audit_hook_denies_non_finite_or_negative_money_fields() -> None:
    log = AuditLog()
    state = _profile_with_n_required_slots_filled(4)
    hook = build_audit_hook(log, "s1", lambda sid: state)

    result = await hook(
        _hook_input("s1", "search_cars", {"max_price_eur": float("nan")}), None, {"signal": None}
    )
    assert result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    result = await hook(
        _hook_input("s1", "search_cars", {"max_price_eur": -100}), None, {"signal": None}
    )
    assert result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


async def test_audit_hook_allows_a_normal_search_with_valid_money_field() -> None:
    log = AuditLog()
    state = _profile_with_n_required_slots_filled(4)
    hook = build_audit_hook(log, "s1", lambda sid: state)
    result = await hook(
        _hook_input("s1", "search_cars", {"max_price_eur": 20000}), None, {"signal": None}
    )
    assert result == {}


async def test_audit_hook_ignores_non_pretooluse_events() -> None:
    log = AuditLog()
    hook = build_audit_hook(log, "s1", lambda sid: None)
    result = await hook({"hook_event_name": "PostToolUse"}, None, {"signal": None})
    assert result == {}
    assert log.for_session("s1") == ()


@pytest.mark.parametrize("filled", [0, 1])
async def test_search_gate_denies_below_the_slot_threshold(filled: int) -> None:
    state = _profile_with_n_required_slots_filled(filled)
    gate = build_search_gate("s1", lambda sid: state)
    decision = await gate("search_cars", {}, ToolPermissionContext())
    assert decision.behavior == "deny"
    assert str(MIN_SLOTS_BEFORE_SEARCH) in decision.message


@pytest.mark.parametrize("filled", [2, 3, 4])
async def test_search_gate_allows_at_or_above_the_slot_threshold(filled: int) -> None:
    state = _profile_with_n_required_slots_filled(filled)
    gate = build_search_gate("s1", lambda sid: state)
    decision = await gate("search_cars", {}, ToolPermissionContext())
    assert decision.behavior == "allow"


async def test_search_gate_only_applies_to_profile_gated_tools() -> None:
    state = _profile_with_n_required_slots_filled(0)
    gate = build_search_gate("s1", lambda sid: state)
    decision = await gate("get_listing", {}, ToolPermissionContext())
    assert decision.behavior == "allow"


def _search_page(*ids: tuple[str, str]) -> dict[str, object]:
    return {"items": [{"source": s, "source_id": sid} for s, sid in ids], "total": len(ids)}


def _search_cars_tool_response(*ids: tuple[str, str]) -> list[dict[str, object]]:
    """**The real shape**, read out of the bundled CLI's own source (D-066): `tool_response`
    is the tool_result block's `content`, i.e. a bare list of content blocks -- *not* a dict
    wrapping a `content` key, which is what D-062's first two attempts assumed and why they
    extracted nothing from searches that had really found cars.
    """
    return [{"type": "text", "text": json.dumps(_search_page(*ids))}]


_ONE_LISTING_PAGE = _search_page(("mock_autobazaar", "AB-1"))
_BLOCK_LIST = [{"type": "text", "text": json.dumps(_ONE_LISTING_PAGE)}]


class _Block:
    """Stands in for a `ToolResultBlock`: the scanner reads `.content` off it, nothing else."""

    def __init__(self, content: object) -> None:
        self.content = content


class _Msg:
    """Stands in for a `UserMessage` carrying tool results."""

    def __init__(self, content: object) -> None:
        self.content = content


_TOOL_RESULT_SHAPES = [
    # The real shape (D-066): a bare content-block list off the tool_result block.
    _BLOCK_LIST,
    json.dumps(_BLOCK_LIST),
    # A `{"content": [...]}` envelope -- accepted too, since the CLI varies this by tool.
    {"content": _BLOCK_LIST},
    json.dumps({"content": _BLOCK_LIST}),
    # `content` collapsed to the parsed page directly.
    {"content": _ONE_LISTING_PAGE},
    {"content": json.dumps(_ONE_LISTING_PAGE)},
    # The block envelope skipped entirely -- just the page.
    _ONE_LISTING_PAGE,
    json.dumps(_ONE_LISTING_PAGE),
]
_TOOL_RESULT_SHAPE_IDS = [
    "bare-block-list-REAL",
    "bare-block-list-json-string",
    "nested-dict",
    "nested-dict-json-string",
    "content-as-page",
    "content-as-json-string",
    "bare-page",
    "bare-json-string",
]


@pytest.mark.parametrize("block_content", _TOOL_RESULT_SHAPES, ids=_TOOL_RESULT_SHAPE_IDS)
def test_extract_candidate_ids_tolerates_every_plausible_result_shape(
    block_content: object,
) -> None:
    assert extract_candidate_ids([_Msg([_Block(block_content)])]) == ("mock_autobazaar:AB-1",)


def test_extract_candidate_ids_collects_across_several_searches_in_one_turn() -> None:
    """D-067: the orchestrator delegates to two `researcher` subagents, so one turn really
    does carry more than one search result -- both must count toward RESEARCH's exit.
    """
    first = _Block(_search_cars_tool_response(("mock_autobazaar", "AB-1")))
    second = _Block(_search_cars_tool_response(("mock_drivenow", "DN-1")))
    ids = extract_candidate_ids([_Msg([first]), _Msg([second])])
    assert ids == ("mock_autobazaar:AB-1", "mock_drivenow:DN-1")


def test_extract_candidate_ids_deduplicates_overlapping_results() -> None:
    block = _Block(_search_cars_tool_response(("mock_autobazaar", "AB-1")))
    ids = extract_candidate_ids([_Msg([block]), _Msg([block])])
    assert ids == ("mock_autobazaar:AB-1",)


def test_extract_candidate_ids_is_empty_for_a_search_that_found_nothing() -> None:
    assert extract_candidate_ids([_Msg([_Block(_search_cars_tool_response())])]) == ()


def test_extract_candidate_ids_ignores_blocks_that_are_not_search_pages() -> None:
    """Any other tool's result reaches the same scan; only a real `SearchPage` counts."""
    other = _Block([{"type": "text", "text": json.dumps({"ok": True})}])
    prose = _Block([{"type": "text", "text": "rendered interview progress"}])
    assert extract_candidate_ids([_Msg([other, prose])]) == ()


def test_extract_candidate_ids_ignores_messages_without_block_content() -> None:
    assert extract_candidate_ids([_Msg("plain string"), _Msg(None)]) == ()


async def test_audit_hook_denies_a_namespaced_search_with_no_profile_started() -> None:
    """D-067: live, tools arrive namespaced (`mcp__market__search_cars`), so this
    profile-gated denial was never actually firing in a real session.
    """
    log = AuditLog()
    hook = build_audit_hook(log, "s1", lambda sid: None)
    result = await hook(_hook_input("s1", "mcp__market__search_cars", {}), None, {"signal": None})
    assert result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


async def test_search_gate_denies_a_namespaced_tool_below_the_threshold() -> None:
    """Gate 3.8's runtime backstop, same D-067 fix."""
    state = _profile_with_n_required_slots_filled(0)
    gate = build_search_gate("s1", lambda sid: state)
    decision = await gate("mcp__market__search_cars", {}, ToolPermissionContext())
    assert decision.behavior == "deny"
