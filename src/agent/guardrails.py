"""Guardrails (PHASE-3 §6): two mechanisms, different jobs.

`PreToolUse` hook: observational and blocking, for every tool call. It always logs (session,
turn, tool, args hash) to the audit trail P9 will persist, and it hard-rejects the two
constitution-shaped violations PHASE-3 §6 names: a `search_cars`/`compare_listings` call
against a session with no `RequirementProfile` started at all, and a monetary field that
isn't a finite, non-negative number. (The plan's phrasing is "a raw `Money` float" -- at the
MCP JSON boundary every number arrives as a JSON number, which Python always decodes as
`int`/`float`; there is no wire-level way to tell "a `Money` built correctly then serialised"
from "a bare float", so the concrete, checkable form of that rule is validity of the number
itself, not its Python type.)

`can_use_tool`: per-call policy with a message the model sees, so it adapts. It enforces
PHASE-3 §8 gate 3.8 -- `search_cars`/`compare_listings` need at least two filled requirement
slots -- as a runtime backstop independent of which subagent is nominally active, because the
interviewer having no search tool only stops the *intended* path; this is what stops the
orchestrator itself from reaching for search early.

Neither of these is what makes `confirm_booking` unreachable -- that's tool visibility
(`src/mcp/audience.py`, PHASE-2 §4). Defence in depth: visibility is the wall, these are the
alarm (PHASE-3 §6).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from claude_agent_sdk.types import (
    CanUseTool,
    HookCallback,
    HookContext,
    HookInput,
    HookJSONOutput,
    PermissionResult,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from src.agent.phase_machine import SessionState

#: Tools whose result depends on a real requirement profile existing, per PHASE-3 §6's
#: named example ("any search_cars with an absent RequirementProfile").
_PROFILE_GATED_TOOLS = frozenset({"search_cars", "compare_listings"})

#: Gate 3.8's threshold: the interview must have filled at least this many required slots
#: before a search tool may run, on any path.
MIN_SLOTS_BEFORE_SEARCH = 2

#: MCP schema fields that carry a monetary amount (PHASE-2's marketplace-mcp tool schemas).
_MONEY_FIELD_SUFFIXES = ("_eur",)

StateLookup = Callable[[str], SessionState | None]
StateSetter = Callable[[str, SessionState], None]


def base_tool_name(tool_name: str) -> str:
    """`"mcp__market__search_cars" -> "search_cars"`. Every tool served through an MCP server
    reaches a hook (and `can_use_tool`) under its *namespaced* name, while every table in this
    module is written in the bare names the tool definitions themselves use.

    Verified live (D-067): a real RESEARCH turn's `PostToolUse` reported
    `mcp__market__search_cars`, so every `tool_name in <frozenset of bare names>` check here
    silently never matched on the live path -- the phase-advance hook, the profile-gated
    denial in the audit hook, and gate 3.8's `can_use_tool` backstop alike. Unit tests all
    passed throughout because they construct hook inputs with bare names, which is exactly the
    blind spot D-015's "no live rehearsal" boundary leaves open. `orchestrator.py`'s
    `_progress_events` already did this same `rsplit`; the guardrails simply never got it.
    """
    return tool_name.rsplit("__", 1)[-1]


def hash_args(args: dict[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    session_id: str
    turn: int
    tool_name: str
    args_hash: str
    ts: str


@dataclass
class AuditLog:
    """In-memory audit trail (gate 3.6). Persistence to a durable store is P9's job; P3
    lands the mechanism every tool call flows through.
    """

    entries: list[AuditEntry] = field(default_factory=list)

    def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    def for_session(self, session_id: str) -> tuple[AuditEntry, ...]:
        return tuple(e for e in self.entries if e.session_id == session_id)


def _filled_required_count(state: SessionState | None) -> int:
    if state is None:
        return 0
    return sum(1 for name in state.profile.REQUIRED if getattr(state.profile, name).is_filled)


def _has_invalid_money_field(tool_input: dict[str, Any]) -> str | None:
    for key, value in tool_input.items():
        if not any(key.endswith(suffix) for suffix in _MONEY_FIELD_SUFFIXES):
            continue
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        if not math.isfinite(value) or value < 0:
            return key
    return None


def build_audit_hook(
    audit_log: AuditLog, session_id: str, state_lookup: StateLookup
) -> HookCallback:
    """The `PreToolUse` `HookCallback` PHASE-3 §6 describes. Registered under
    `hooks={"PreToolUse": [HookMatcher(hooks=[this])]}` in `ClaudeAgentOptions`.

    Bound to *this app's* `session_id` up front, exactly as `build_search_gate` already is,
    rather than reading `hook_input["session_id"]` -- that field carries the **CLI's own**
    session id (a UUID it mints for itself; `build_options` deliberately no longer sets one),
    which no `SessionState` is ever stored under. Looking state up by it always returned
    `None`, so `_filled_required_count` always read 0 and the profile-gated denial below fired
    on *every* search, and every audit entry was filed under an id `for_session` could never
    retrieve. Both were invisible until D-067's `base_tool_name` fix finally let the tool-name
    check match a live namespaced call -- at which point the denial started firing for real and
    blocked the search outright.
    """

    async def _hook(
        hook_input: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        if hook_input["hook_event_name"] != "PreToolUse":
            return {}

        tool_name = hook_input["tool_name"]
        tool_input = hook_input["tool_input"]
        state = state_lookup(session_id)

        audit_log.record(
            AuditEntry(
                session_id=session_id,
                turn=state.total_turns if state is not None else 0,
                tool_name=tool_name,
                args_hash=hash_args(tool_input),
                ts=datetime.now(UTC).isoformat(),
            )
        )

        if base_tool_name(tool_name) in _PROFILE_GATED_TOOLS and _filled_required_count(state) == 0:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{tool_name}: no RequirementProfile has been started for this session yet"
                    ),
                }
            }

        bad_field = _has_invalid_money_field(tool_input)
        if bad_field is not None:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{tool_name}: {bad_field!r} is not a finite, non-negative amount"
                    ),
                }
            }

        return {}

    return _hook


def build_search_gate(session_id: str, state_lookup: StateLookup) -> CanUseTool:
    """`can_use_tool` (PHASE-3 §6, gate 3.8): deny `search_cars`/`compare_listings` before
    two required slots are filled, with a message the model sees and can act on -- unlike
    the hook's hard rejection, this is meant to change what the model tries next.

    Bound to one session's state up front, since `can_use_tool` carries no session id of
    its own the way `PreToolUse`'s hook input does.
    """

    async def _can_use_tool(
        tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext
    ) -> PermissionResult:
        if base_tool_name(tool_name) in _PROFILE_GATED_TOOLS:
            state = state_lookup(session_id)
            filled = _filled_required_count(state)
            if filled < MIN_SLOTS_BEFORE_SEARCH:
                return PermissionResultDeny(
                    message=(
                        f"{tool_name} needs at least {MIN_SLOTS_BEFORE_SEARCH} filled "
                        f"requirement slots; only {filled} are filled. Keep interviewing "
                        "before searching."
                    )
                )
        return PermissionResultAllow()

    return _can_use_tool


def _maybe_json(value: Any) -> Any:
    """JSON-decodes a string in place, leaving anything else alone -- for the case where a
    payload arrives serialised into a text block rather than already parsed.
    """
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _search_page_payload(tool_response: Any) -> dict[str, Any] | None:
    """Digs the `SearchPage` JSON out of whatever `PostToolUse` handed over for a `search_cars`
    call, and returns it only if it really is a search page (has an `items` list).

    **The shape is read from the CLI's own source, not guessed** (D-066). The bundled
    `claude.exe` builds the hook payload as::

        for (let b of _.message.content)
          if (b.type === "tool_result") g.set(b.tool_use_id, b.content)
        ... tool_response: g.get(b.id)

    -- so `tool_response` is the tool_result block's **`content`**, which for an MCP tool is a
    *bare list of content blocks*: `[{"type": "text", "text": "<SearchPage JSON>"}]`. Not a
    dict wrapping a `content` key, which is what D-062's first two attempts both assumed and
    is exactly why they silently extracted nothing from a search that had really found cars.

    The dict forms are still accepted below because the same CLI demonstrably varies this by
    tool (its own Bash hook reads `tool_response.stdout`), and because an MCP tool result may
    legitimately carry a plain string instead of a block list.
    """
    tool_response = _maybe_json(tool_response)

    if isinstance(tool_response, dict):
        # Already the page itself, or a `{"content": ...}` envelope around it.
        if isinstance(tool_response.get("items"), list):
            return tool_response
        content: Any = tool_response.get("content")
    else:
        # The real shape: the content list (or a plain string) straight off the block.
        content = tool_response

    content = _maybe_json(content)
    if isinstance(content, dict):
        return content if isinstance(content.get("items"), list) else None
    if not isinstance(content, list) or not content:
        return None

    first = content[0]
    if not isinstance(first, dict):
        return None
    payload = _maybe_json(first.get("text"))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return None
    return payload




def extract_candidate_ids(messages: Iterable[Any]) -> tuple[str, ...]:
    """Every `"source:source_id"` any `search_cars` call in this turn returned, in order, with
    duplicates dropped -- what `phase_machine._exit_predicate_met` needs to let RESEARCH end.

    **Scans the message stream rather than a `PostToolUse` hook, and that is the whole point**
    (D-067). A hook was the obvious mechanism and it silently never fires for these searches:
    `prompts/orchestrator_system.md` tells the orchestrator to delegate searching to two
    `researcher` subagents, and a subagent's tool calls do not reach the parent session's
    `PostToolUse` -- instrumenting it live showed it firing only for `Agent`, never once for
    `search_cars`, while the searches demonstrably ran. Subagent traffic *does* arrive in
    `ClaudeSDKClient.receive_response()`, so reading tool *results* off the finished turn
    catches every search whoever made it.

    Deliberately permissive about which block carried the result and strict about what counts
    as one: any `ToolResultBlock`-shaped object whose content parses as a `SearchPage` (has an
    `items` list) contributes; anything else is ignored. That way this neither depends on the
    tool-name spelling (`mcp__market__search_cars` vs `search_cars`, D-067's first wrong fix)
    nor mistakes some other tool's payload for a search page.
    """
    ids: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            block_content = getattr(block, "content", None)
            if block_content is None:
                continue
            payload = _search_page_payload(block_content)
            if payload is None:
                continue
            for item in payload["items"]:
                if not isinstance(item, dict):
                    continue
                source, source_id = item.get("source"), item.get("source_id")
                if isinstance(source, str) and isinstance(source_id, str):
                    ids.append(f"{source}:{source_id}")
    return tuple(dict.fromkeys(ids))
