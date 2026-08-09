"""Live orchestration (PHASE-3 §4): wires the three model-facing MCP builds, the subagent
roster, the guardrail hooks and durable session state into a `ClaudeSDKClient` session.

`DEMO_MODE=true` never constructs this -- `src/agent/demo.py`'s `run_demo_session` is the
whole flow with no SDK, no subprocess, and no credentials involved (CONSTITUTION III.7).
This module is what a real judge session or a rehearsed live demo runs, and it is
deliberately not exercised by `scripts/gate_phase3.py`: a check that needs the `claude` CLI
and live credentials cannot run deterministically in CI, which is the same reasoning
DECISIONS.md D-012 gives for keeping gate 2.6 off a live session. What the gate *can* and
does check is every piece this module is built from -- the phase machine, the guardrails,
the roster, the prompt files -- independently and deterministically.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    Message,
)

from src.adapters.dealer_store import DealerDirectory, InMemoryDealerDirectory
from src.adapters.store import InMemoryListingStore, ListingStore
from src.agent.guardrails import (
    AuditLog,
    build_audit_hook,
    build_search_gate,
    extract_candidate_ids,
)
from src.agent.model_catalog import default_interview_model_id
from src.agent.phase_machine import Phase, SessionState, advance, new_session
from src.agent.prompts import load_prompt
from src.agent.session_store import InMemorySessionStateStore, SessionStateStore
from src.agent.subagents import ORCHESTRATOR_MODEL, build_roster
from src.mcp.booking.server import build_booking_server
from src.mcp.marketplace.server import build_marketplace_server
from src.mcp.ui.actions import UIAction, to_user_turn
from src.mcp.ui.server import build_ui_server
from src.mcp.ui.sink import QueueUISink
from src.mcp.ui.surfaces import SurfaceRegistry

DEMO_MODE_ENV = "DEMO_MODE"

#: PLAN-00 §6.7's routing is `effort=high` plus adaptive thinking. Both are per-turn cost
#: multipliers on top of the model choice (`subagents.ORCHESTRATOR_MODEL`), so both are
#: env-selectable for the same reason it is, and both default to the cheap setting. Set
#: `CARDINAL_AGENT_EFFORT=high` / `CARDINAL_AGENT_THINKING=adaptive` for the plan's routing.
AGENT_EFFORT: Any = os.environ.get("CARDINAL_AGENT_EFFORT", "low").strip()
AGENT_THINKING: Any = {"type": os.environ.get("CARDINAL_AGENT_THINKING", "disabled").strip()}


def demo_mode_enabled() -> bool:
    """CONSTITUTION III.7's switch. Callers at the API layer check this before ever
    constructing a `CardinalOrchestrator` -- `src/agent/demo.py` is the alternative path.
    """
    return os.environ.get(DEMO_MODE_ENV, "").strip().lower() in {"1", "true", "yes"}


#: Tool name -> what to say the agent is doing. Anything unlisted streams no status rather
#: than leaking a raw `mcp__market__search_cars` at the person (CONSTITUTION II.6: the user
#: never learns marketplaces are plural, let alone what the tools are called).
_TOOL_STATUS: dict[str, str] = {
    "search_cars": "Searching the marketplaces",
    "compare_listings": "Comparing the shortlist",
    "get_listing": "Reading a listing in detail",
    "get_quote": "Pricing it up",
    "check_availability": "Checking availability",
    "render_progress": "Updating your requirements",
    "render_results": "Drawing up the shortlist",
    "render_detail": "Opening the detail view",
    "render_tco": "Running the cost comparison",
    "open_booking_form": "Opening the booking form",
}


def _progress_events(message: Message) -> list[dict[str, Any]]:
    """Turns one SDK message into zero or more browser-bound progress events.

    Only *top-level assistant* prose streams as chat. `receive_response` also yields every
    subagent's own traffic, including the `UserMessage` carrying the prompt each subagent was
    launched with -- streaming those verbatim published the interviewer's system prompt into
    the chat rail as if the agent had said it. Subagent activity is still represented, but as
    a status line, which is what a person actually wants from it.
    """
    events: list[dict[str, Any]] = []
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return events
    from_subagent = getattr(message, "parent_tool_use_id", None) is not None
    is_assistant = isinstance(message, AssistantMessage)
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            if is_assistant and not from_subagent:
                events.append({"kind": "agent_text", "text": text})
            continue
        name = getattr(block, "name", None)
        if isinstance(name, str):
            status = _TOOL_STATUS.get(name.rsplit("__", 1)[-1])
            if status is not None:
                events.append({"kind": "agent_status", "status": status})
    return events


class CardinalOrchestrator:
    """One process's worth of live-session wiring, shared across however many concurrent
    sessions it serves. Per-session state lives in `self._states`, keyed by `session_id`,
    which is also what the guardrail closures look up by by (PHASE-3 §6).
    """

    def __init__(
        self,
        *,
        store: ListingStore | None = None,
        session_store: SessionStateStore | None = None,
        dealers: DealerDirectory | None = None,
    ) -> None:
        self._store = store or InMemoryListingStore.seeded()
        #: PLAN-02 P13 -- who is selling each listing, so `render_results` can attribute a
        #: card to a business a buyer can call. Defaults to the same generated directory the
        #: seeded in-memory catalogue's `dealer_id`s point at; anything else would resolve to
        #: `None` and silently drop attribution rather than fail loudly.
        self._dealers = dealers or InMemoryDealerDirectory.seeded()
        self._session_store = session_store or InMemorySessionStateStore()
        self._audit_log = AuditLog()
        self._states: dict[str, SessionState] = {}
        #: One `ui-mcp` surface registry and one outbound-message queue per session (PHASE-6
        #: SS6) -- rebuilding `ClaudeAgentOptions` every `send()` call must not also reset
        #: surface identity, or every turn would look like the first `render_results` call
        #: (gate 6.6's whole point) instead of an update.
        self._ui_registries: dict[str, SurfaceRegistry] = {}
        self._ui_sinks: dict[str, QueueUISink] = {}
        #: PHASE-6 SS6's action round-trip: every `{surface, component, action, payload}`
        #: click `src/api`'s `POST /sessions/{id}/actions` receives, in the order received --
        #: gate 6.5's evidence that a click reached "the agent session" with full provenance,
        #: not just that the HTTP call returned 200.
        self._ui_actions: dict[str, list[dict[str, Any]]] = {}
        #: One *connected* `ClaudeSDKClient` per session, held open across turns. A client per
        #: turn was the original shape and it broke twice over: the CLI rejects a second
        #: connection carrying a session id it already knows ("Session ID ... is already in
        #: use"), so only a session's first turn ever succeeded, and even that turn started
        #: from an empty transcript -- an interview agent that cannot remember the previous
        #: answer is not an interview agent. `send` serialises turns per session through
        #: `_client_locks` so two in-flight messages can't interleave on one client.
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._client_locks: dict[str, asyncio.Lock] = {}
        #: D-056: which `provider/model` id (or `model_catalog.CLAUDE_MODEL_ID`) a session's
        #: INTERVIEW phase runs on. `src/api/main.py` is what actually branches a turn between
        #: `interview_chat.interview_turn` and `self.send` based on this and the session's
        #: current `Phase` -- this class only remembers the choice per session, the same
        #: bookkeeping-dict posture as `_ui_registries`/`_ui_sinks` above. Only ever written
        #: by `set_model`; an absent entry means "whatever the deployment's default is",
        #: resolved at read time by `model_for` (D-059) rather than frozen in at construction.
        self._session_models: dict[str, str] = {}
        #: Sessions whose first post-INTERVIEW turn has already told the (until-now-unused)
        #: Claude client what the alternate model's interview already gathered. Without this,
        #: RESEARCH would start from a `ClaudeSDKClient` that has never seen a single message
        #: and would re-run the interview it has no memory of.
        self._handoff_primed: set[str] = set()

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    def state(self, session_id: str) -> SessionState | None:
        return self._states.get(session_id)

    def update_state(self, session_id: str, state: SessionState) -> None:
        """Writes back a `SessionState` this orchestrator didn't itself produce -- the one
        thing `interview_chat.interview_turn`'s alternate-model path needs from here, so a
        later `send()` call's own `start_or_resume` finds the profile it gathered instead of
        starting Claude's session from a blank one.
        """
        self._states[session_id] = state

    def model_for(self, session_id: str) -> str:
        return self._session_models.get(session_id) or default_interview_model_id()

    def set_model(self, session_id: str, model_id: str) -> None:
        self._session_models[session_id] = model_id

    def needs_handoff_priming(self, session_id: str) -> bool:
        """True at most once per session: the first time a turn reaches Claude after an
        alternate model ran INTERVIEW, `src/api/main.py` uses this to decide whether to prime
        the otherwise-blank `ClaudeSDKClient` with what was already gathered. Marks itself
        used on the way out rather than needing a separate `mark_primed` call every caller has
        to remember, since there is exactly one caller and exactly one moment this matters.
        """
        if session_id in self._handoff_primed:
            return False
        self._handoff_primed.add(session_id)
        return True

    def ui_sink(self, session_id: str) -> QueueUISink:
        """The same queue a session's `ui-mcp` tool handlers push into -- `src/api`'s SSE
        route (PHASE-6 SS6) reads this to stream A2UI messages to the browser.
        """
        if session_id not in self._ui_sinks:
            self._ui_sinks[session_id] = QueueUISink()
        return self._ui_sinks[session_id]

    def ui_registry(self, session_id: str) -> SurfaceRegistry:
        """The same `SurfaceRegistry` a live session's `build_options` would create for this
        session id (gate 6.6's surface-identity guarantee) -- exposed so `src/agent/demo_stream`
        can share it, rather than a demo session's surfaces never being create-once-then-update
        the way a live session's are.
        """
        return self._ui_registries.setdefault(session_id, SurfaceRegistry())

    def record_action(self, session_id: str, action: UIAction) -> dict[str, Any]:
        """Turns one renderer action into a user turn with structured provenance and files it
        under the session -- the same shape a live `ClaudeSDKClient.query` would eventually be
        given as this session's next turn, once P7/P8 wire an MCP App's own actions through the
        same path this one already proves out for A2UI surfaces.
        """
        turn = to_user_turn(action)
        self._ui_actions.setdefault(session_id, []).append(turn)
        return turn

    def actions_for(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._ui_actions.get(session_id, []))

    async def start_or_resume(self, session_id: str) -> SessionState:
        """Gate 3.2: a session surviving a process restart is `session_store.load` finding
        what an earlier process's `save` wrote, keyed by the same `session_id`.
        """
        if session_id in self._states:
            return self._states[session_id]
        restored = await self._session_store.load(session_id)
        state = restored if restored is not None else new_session(session_id)
        self._states[session_id] = state
        return state

    def build_options(self, session_id: str) -> ClaudeAgentOptions:
        """PHASE-3 §4's `ClaudeAgentOptions` shape, built for real: `mcp_servers` are the
        three *model-facing* P2 builds (`confirm_booking` and `submit_booking_draft` are
        simply absent -- CONSTITUTION I.2, gate 2.6), `agents` is the roster from
        `subagents.py`, and the guardrails close over this session's own state.
        """
        audit_hook = build_audit_hook(self._audit_log, session_id, self.state)
        search_gate = build_search_gate(session_id, self.state)
        self._ui_registries.setdefault(session_id, SurfaceRegistry())

        def _current_phase() -> str:
            state = self.state(session_id)
            return state.phase.value if state is not None else "interview"

        return ClaudeAgentOptions(
            model=ORCHESTRATOR_MODEL,
            effort=AGENT_EFFORT,
            thinking=AGENT_THINKING,
            system_prompt=load_prompt("orchestrator_system"),
            mcp_servers={
                "market": build_marketplace_server(self._store, audience="model"),
                "ui": build_ui_server(
                    audience="model",
                    session_id=session_id,
                    sink=self.ui_sink(session_id),
                    registry=self._ui_registries[session_id],
                    store=self._store,
                    dealers=self._dealers,
                    phase=_current_phase,
                ),
                "booking": build_booking_server(
                    audience="model",
                    session_id=session_id,
                    sink=self.ui_sink(session_id),
                    store=self._store,
                    dealers=self._dealers,
                ),
            },
            agents=build_roster(),
            hooks={"PreToolUse": [HookMatcher(hooks=[audit_hook])]},
            can_use_tool=search_gate,
            # `session_id` is deliberately left unset: the CLI mints its own and this process
            # holds the resulting client open (`self._clients`), which is what actually carries
            # conversation context between turns. Pinning our own app-level id here instead is
            # what produced "Session ID ... is already in use" on every turn after the first.
        )

    async def _client_for(self, session_id: str) -> ClaudeSDKClient:
        """Connect on first use, reuse forever after. The guardrail/phase closures baked into
        `build_options` read `self.state(session_id)` when they *fire*, not when they're built,
        so options constructed once at connect time still see each later turn's phase.
        """
        client = self._clients.get(session_id)
        if client is None:
            client = ClaudeSDKClient(options=self.build_options(session_id))
            await client.connect()
            self._clients[session_id] = client
        return client

    async def send(self, session_id: str, utterance: str) -> list[Message]:
        """One user turn against a live session, on this session's own long-lived client.

        Slot extraction, phase advancement and research dispatch happen inside the live
        session via the subagent roster and tool calls, not here -- this method's job is
        only the SDK transport, mirroring how `demo.py` keeps those concerns
        (`interview.py`, `research.py`) as the one shared implementation.
        """
        await self.start_or_resume(session_id)
        lock = self._client_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            client = await self._client_for(session_id)
            sink = self.ui_sink(session_id)
            messages: list[Message] = []
            await client.query(utterance)
            async for message in client.receive_response():
                messages.append(message)
                for event in _progress_events(message):
                    # Same SSE channel the A2UI surfaces use, discriminated by `kind` exactly
                    # the way `mcp_app_open` already is. A turn takes tens of seconds; without
                    # this the browser has nothing to show for any of it but a spinner.
                    await sink.push([event])
            self._advance_research_from(session_id, messages)
            return messages

    def _advance_research_from(self, session_id: str, messages: list[Message]) -> None:
        """Fills `candidate_ids` from whatever this turn's `search_cars` calls actually found,
        then lets `phase_machine.advance()` decide -- the piece of "the phase is decided by
        code, not by you" (`prompts/orchestrator_system.md`) that the live path never had.

        **Reads the message stream, not a `PostToolUse` hook** (D-067). A hook was the obvious
        mechanism and it does not work here: the orchestrator delegates searching to
        `researcher` subagents (its own prompt tells it to), and a subagent's tool calls never
        reach the parent session's `PostToolUse` -- instrumenting the hook live showed it
        firing only for `Agent`, never once for `search_cars`, while the searches themselves
        plainly happened. Subagent traffic *does* come back in `receive_response()`'s stream,
        so scanning the completed turn catches every search regardless of which agent ran it.
        """
        state = self.state(session_id)
        if state is None or state.phase is not Phase.RESEARCH:
            return
        found = extract_candidate_ids(messages)
        if not found:
            return
        merged = tuple(dict.fromkeys((*state.candidate_ids, *found)))
        self.update_state(session_id, advance(state.model_copy(update={"candidate_ids": merged})))

    async def aclose(self) -> None:
        """Disconnects every live session's client -- called from the API's lifespan shutdown
        so a reload doesn't leave orphaned `claude` subprocesses behind.
        """
        for client in self._clients.values():
            try:
                await client.disconnect()
            except Exception:
                # Shutdown must not fail on an already-dead client.
                pass
        self._clients.clear()
