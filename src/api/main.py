"""FastAPI. Transport only -- routes, no business logic (PLAN-00 §2).

This is the only package in `src/` allowed to import `fastapi`. `src/domain`, `src/adapters`
and `src/agent` are held to that by a ruff ban *and* by `tests/test_layer_boundary.py`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from claude_agent_sdk import AssistantMessage, Message, TextBlock
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.adapters.booking_store import BookingStore, InMemoryBookingStore
from src.adapters.db.booking_store import PostgresBookingStore
from src.adapters.db.session import database_url, dispose_engine, session_factory
from src.adapters.db.store import PostgresListingStore
from src.adapters.registry import registered_adapters, registered_source_names
from src.adapters.store import InMemoryListingStore, ListingStore
from src.agent import demo_stream
from src.agent.interview_chat import handoff_summary, interview_turn
from src.agent.model_catalog import CLAUDE_MODEL_ID, visible_models
from src.agent.model_catalog import find as find_model
from src.agent.orchestrator import CardinalOrchestrator
from src.agent.phase_machine import Phase
from src.agent.providers import ProviderError
from src.agent.tracing import configure_tracing
from src.mcp.apps.audit import AppAuditLog
from src.mcp.apps.proxy import AppRpcError, call_view_rpc
from src.mcp.booking.resources import ALLOWED_VIEW_TOOLS, BOOKING_FORM_URI, CHECKOUT_URI
from src.mcp.booking.server import build_booking_server
from src.mcp.ui.actions import InvalidActionError, parse_action

logger = logging.getLogger(__name__)

DEMO_MODE_ENV = "DEMO_MODE"
REPO_ROOT = Path(__file__).resolve().parents[2]

#: `booking-mcp`'s standalone HTTP transport (PHASE-2's `src/mcp/booking/http.py`). Locally and
#: in every gate through P10, started lazily as a real subprocess -- `python -m
#: src.mcp.booking.http` -- on this loopback-only port. In Docker (PHASE-11 §3), `booking` is
#: its own compose service with its own hostname, so `CARDINAL_BOOKING_MCP_URL` overrides this
#: and `_ensure_booking_mcp_http` becomes a no-op -- there is nothing for this process to spawn
#: or own the lifecycle of. Reached from `mcp_app_rpc` below, server-side, never proxied to or
#: exposed on any route the browser can reach (CONSTITUTION II.5).
BOOKING_MCP_HOST = "127.0.0.1"
BOOKING_MCP_PORT = 8100
ENV_BOOKING_MCP_URL = "CARDINAL_BOOKING_MCP_URL"
BOOKING_MCP_URL = os.environ.get(
    ENV_BOOKING_MCP_URL, f"http://{BOOKING_MCP_HOST}:{BOOKING_MCP_PORT}/mcp/"
)

#: Which MCP server a resource's `tools/call`/`resources/read` traffic belongs to, and which
#: tool names a *view* (as opposed to the model) may invoke for it. `ui://checkout/payment`
#: is P8's second entry -- a second resource on the same `booking-mcp` server, not a second
#: host implementation (PROGRESS.md's note when P7 landed).
RESOURCE_ROUTES: dict[str, frozenset[str]] = {
    BOOKING_FORM_URI: ALLOWED_VIEW_TOOLS[BOOKING_FORM_URI],
    CHECKOUT_URI: ALLOWED_VIEW_TOOLS[CHECKOUT_URI],
}


def demo_mode() -> bool:
    return os.environ.get(DEMO_MODE_ENV, "").lower() in {"1", "true", "yes"}


def build_store() -> tuple[ListingStore, str]:
    """Postgres when configured, the generated catalogue otherwise.

    CONSTITUTION III.7: the whole flow must run with the environment unset. Falling back to
    the in-memory catalogue rather than failing to boot is what makes that true here.
    """
    if demo_mode() or database_url() is None:
        return InMemoryListingStore.seeded(), "memory"
    return PostgresListingStore(session_factory()), "postgres"


def build_booking_store(backend: str) -> BookingStore:
    """Same split as `build_store`, one table over -- `PostgresBookingStore` when the app is
    actually running against Postgres, `InMemoryBookingStore` otherwise (`DEMO_MODE`, no
    `CARDINAL_DATABASE_URL`, or a plain `TestClient(app)` in a unit test).
    """
    if backend == "postgres":
        return PostgresBookingStore(session_factory())
    return InMemoryBookingStore()


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


async def _ensure_booking_mcp_http(app: FastAPI) -> None:
    """Starts `booking-mcp`'s standalone HTTP transport on first use, not on every app boot --
    so gate 6.5-style `TestClient(app)` tests that never touch `/mcp-apps/*` don't each pay for
    (or risk a port collision from) a subprocess they don't need. Idempotent: a second caller
    mid-startup waits on the same lock rather than racing a second subprocess into existence.

    A no-op when `CARDINAL_BOOKING_MCP_URL` is set (PHASE-11 §3's Docker shape) -- `booking` is
    a separately deployed, separately owned process there, and this API process has no business
    spawning or terminating it.
    """
    if ENV_BOOKING_MCP_URL in os.environ:
        return
    lock: asyncio.Lock = app.state.booking_mcp_lock
    async with lock:
        already_running = app.state.booking_mcp_process is not None or _port_open(
            BOOKING_MCP_HOST, BOOKING_MCP_PORT
        )
        if already_running:
            return
        process = await asyncio.to_thread(
            subprocess.Popen,
            [sys.executable, "-m", "src.mcp.booking.http"],
            cwd=str(REPO_ROOT),
        )
        app.state.booking_mcp_process = process
        for _ in range(50):  # ~5s at 100ms
            if _port_open(BOOKING_MCP_HOST, BOOKING_MCP_PORT):
                return
            await asyncio.sleep(0.1)
        raise RuntimeError("booking-mcp HTTP server did not start within 5s")


def _instrument_tracing() -> None:
    """PHASE-9 §3: one line auto-generates spans for every live model request and tool
    execution; `configure_tracing()` is what makes them (and every hand-written span this
    codebase adds on top) actually go somewhere. Fire-and-forget, per PHASE-9 §8's own risk
    table -- a bonus phase's instrumentation must never be why the app fails to boot.
    """
    try:
        configure_tracing()
        from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor

        ClaudeAgentSDKInstrumentor().instrument()
    except Exception:
        logger.warning("tracing instrumentation failed to start; continuing without it")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _instrument_tracing()
    store, backend = build_store()
    app.state.store = store
    app.state.backend = backend
    #: PHASE-8: the durable booking table, shared across every `/mcp-apps/*/rpc` call in this
    #: process -- see `src/mcp/booking/tools.py`'s own note on why a fresh store per request
    #: would silently forget a minted gesture token or an in-flight idempotency key.
    app.state.booking_store = build_booking_store(backend)
    #: PHASE-6 SS6: the orchestrator outlives any one request so a session's `SurfaceRegistry`
    #: and `QueueUISink` (gate 6.6's identity guarantee) survive between turns.
    app.state.orchestrator = CardinalOrchestrator(store=store)
    #: PHASE-7: view-initiated RPC audit trail (SS5.5) and the lazily-started booking-mcp HTTP
    #: subprocess `_ensure_booking_mcp_http` owns -- both process-lifetime, like the orchestrator.
    app.state.app_audit_log = AppAuditLog()
    app.state.booking_mcp_process = None
    app.state.booking_mcp_lock = asyncio.Lock()
    try:
        yield
    finally:
        await app.state.orchestrator.aclose()
        if backend == "postgres":
            await dispose_engine()
        process: subprocess.Popen[bytes] | None = app.state.booking_mcp_process
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


app = FastAPI(title="Cardinal", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness plus a listing count -- gate 1.10 asserts both.

    A health check that only says "the process is up" would have passed happily against an
    empty database on demo morning.
    """
    store: ListingStore = app.state.store
    total = await store.count()
    per_source = {name: await store.count(sources=[name]) for name in registered_source_names()}
    return {
        "status": "ok",
        "backend": app.state.backend,
        "demo_mode": demo_mode(),
        "listings": total,
        "sources": per_source,
    }


@app.get("/adapters")
async def adapters() -> list[dict[str, str]]:
    store: ListingStore = app.state.store
    return [adapter.info().model_dump(mode="json") for adapter in registered_adapters(store)]


@app.get("/models")
async def models() -> list[dict[str, Any]]:
    """The INTERVIEW-phase model picker's catalog (D-056) -- `web/`'s chat rail renders one
    entry per row. Whether a given provider's key is actually set is discovered when a session
    picks it (`POST /sessions/{id}/model` 422s with a plain message), not hidden from the list
    -- a key someone hasn't set yet is not the same as a model that doesn't exist.

    Empty unless `CARDINAL_SHOW_MODEL_PICKER` is on (D-059), which is what hides the picker:
    the route stays, so `POST /sessions/{id}/model` is still a supported way to override a
    session, but the browser is told nothing about which models exist by default.
    """
    return [dict(m) for m in visible_models()]


@app.post("/sessions/{session_id}/model")
async def set_session_model(session_id: str, request: Request) -> dict[str, Any]:
    """Picks which model drives this session's INTERVIEW phase (D-056) -- must be called, if
    at all, before the first `POST /sessions/{id}/messages`. Defaults to `CLAUDE_MODEL_ID`
    (today's only behaviour) when never called, so this route is additive: a session that
    never touches it is unaffected.
    """
    body = await request.json()
    model_id = body.get("model_id")
    known = isinstance(model_id, str) and (model_id == CLAUDE_MODEL_ID or find_model(model_id))
    if not known:
        raise HTTPException(status_code=422, detail=f"unknown model_id: {model_id!r}")
    orchestrator: CardinalOrchestrator = app.state.orchestrator
    orchestrator.set_model(session_id, model_id)
    return {"model_id": model_id}


def _sse_frame(message: dict[str, Any]) -> str:
    return f"data: {json.dumps(message)}\n\n"


@app.get("/sessions/{session_id}/events")
async def session_events(session_id: str) -> StreamingResponse:
    """SSE agent->client transport (PHASE-6 SS6): every A2UI message a `ui-mcp` tool handler
    pushes for this session, in order, framed as `text/event-stream`. One `createSurface`
    the first time a surface kind is rendered, `updateComponents`/`updateDataModel` after --
    `src/mcp/ui/surfaces.py`'s `SurfaceRegistry` decides which, this route just relays.
    """
    orchestrator: CardinalOrchestrator = app.state.orchestrator
    sink = orchestrator.ui_sink(session_id)

    async def stream() -> AsyncIterator[str]:
        async for message in sink.stream():
            yield _sse_frame(message)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/actions")
async def session_actions(session_id: str, request: Request) -> dict[str, Any]:
    """Client->agent transport (PHASE-6 SS6): the renderer's `actionHandler` posts here. The
    action is parsed into `{surface, component, action, payload}` provenance and filed as this
    session's next turn -- gate 6.5's round-trip, minus the live model turn itself (D-015: a
    check needing a live `ClaudeSDKClient` session cannot run deterministically in CI).

    In a `DEMO_MODE` session that `run_streamed_demo` drove, an `explain` click on a rendered
    `CarCard` is additionally handed to `demo_stream.handle_explain_action`, which pushes the
    real `ScoreBreakdown` `rank()` already computed for that listing (PHASE-11's own beat: "the
    agent opening a score breakdown"); an `expand_tco` click on the TCO surface is handed to
    `handle_expand_tco_action` the same way, pushing the real itemised `TcoComparison` beat 2
    already computed (D-061's radar chart). Filed as a plain user turn either way, live-session
    parity intact.
    """
    body = await request.json()
    orchestrator: CardinalOrchestrator = app.state.orchestrator
    try:
        action = parse_action(body)
    except InvalidActionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if demo_mode() and action.action == "explain":
        await demo_stream.handle_explain_action(
            session_id,
            sink=orchestrator.ui_sink(session_id),
            registry=orchestrator.ui_registry(session_id),
            payload=action.payload,
        )
    if demo_mode() and action.action == "expand_tco":
        await demo_stream.handle_expand_tco_action(
            session_id,
            sink=orchestrator.ui_sink(session_id),
            registry=orchestrator.ui_registry(session_id),
        )
    return orchestrator.record_action(session_id, action)


def _extract_assistant_text(messages: list[Message]) -> list[str]:
    """One string per top-level `AssistantMessage`, its `TextBlock`s concatenated in order --
    what a chat rail renders as one bubble. Tool-use/tool-result/thinking blocks carry no text
    a user turn's reply should show verbatim, so they're dropped rather than passed through,
    and a message with a `parent_tool_use_id` is a *subagent's* traffic, not the agent talking
    to the user.
    """
    texts: list[str] = []
    for message in messages:
        if not isinstance(message, AssistantMessage) or message.parent_tool_use_id is not None:
            continue
        blocks = [block.text for block in message.content if isinstance(block, TextBlock)]
        if blocks:
            texts.append("".join(blocks))
    return texts


@app.post("/sessions/{session_id}/messages")
async def session_messages(session_id: str, request: Request) -> dict[str, Any]:
    """Client->agent transport for a live session's plain-text turns -- the counterpart
    `POST /sessions/{id}/actions` never was: that route files a renderer *action* as a turn,
    this route is what a typed chat message becomes.

    Two paths, chosen by `orchestrator.model_for(session_id)` (D-056, default
    `CLAUDE_MODEL_ID` -- unset unless `POST /sessions/{id}/model` was called, so a session
    that never touches model selection is on exactly the path it always was):

    - `CLAUDE_MODEL_ID`: unchanged -- `CardinalOrchestrator.send` (PHASE-3 §4) does the SDK
      round-trip; any `ui-mcp`/`booking-mcp` tool calls it makes land on the session's
      existing `UISink` and reach the browser over the already-open SSE stream.
    - a `provider/model` id, while still in INTERVIEW: `interview_chat.interview_turn` runs
      instead -- no MCP, no subagents, no tools, scoped to the conversational Q&A only
      (the "interview only" boundary this feature was built to). Once that phase advances,
      later turns on the same session fall through to the Claude branch below unchanged,
      primed once with `handoff_summary` so RESEARCH doesn't start from a blank session that
      has to re-run an interview it never actually had.

    403 in `DEMO_MODE`: that mode's whole flow (CONSTITUTION III.7) runs with no
    `ClaudeSDKClient`, no subprocess and no credentials; routing a message here instead of
    `POST /demo/{id}/start` would construct one anyway.
    """
    if demo_mode():
        raise HTTPException(
            status_code=403, detail="DEMO_MODE sessions start via POST /demo/{id}/start, not chat"
        )
    body = await request.json()
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=422, detail="expected {text: non-empty string}")

    orchestrator: CardinalOrchestrator = app.state.orchestrator
    model_id = orchestrator.model_for(session_id)

    if model_id != CLAUDE_MODEL_ID:
        state = await orchestrator.start_or_resume(session_id)
        if state.phase is Phase.INTERVIEW:
            try:
                turn = await interview_turn(state, text, model_id)
            except ProviderError as exc:
                raise HTTPException(status_code=502, detail=f"{model_id}: {exc}") from exc
            orchestrator.update_state(session_id, turn.state)
            # The Claude branch below streams its reply over SSE as the turn runs
            # (`agent_text`, `_progress_events`) and the browser relies on exactly that --
            # `App.tsx`'s `send()` discards this HTTP response body on purpose to avoid
            # showing the same reply twice. This path has no streaming turn to hook into
            # (one plain call, then done), so it has to push the identical `agent_text`
            # event itself or the browser never learns the reply happened at all.
            sink = orchestrator.ui_sink(session_id)
            await sink.push([{"kind": "agent_text", "text": turn.reply}])
            return {"messages": [{"role": "assistant", "text": turn.reply}]}
        if orchestrator.needs_handoff_priming(session_id):
            text = handoff_summary(state) + text

    try:
        messages = await orchestrator.send(session_id, text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"live turn failed: {exc}") from exc

    return {
        "messages": [
            {"role": "assistant", "text": reply} for reply in _extract_assistant_text(messages)
        ]
    }


#: Session ids with a streamed demo run already in flight, so a double click on "Start Demo"
#: (or a Playwright retry) joins the same run instead of racing a second one against the same
#: `SurfaceRegistry` (gate 6.6's identity guarantee assumes one writer per session).
_demo_runs_in_flight: set[str] = set()

#: A bare `asyncio.create_task` result with nothing holding a reference to it is eligible for
#: garbage collection mid-run (a real asyncio gotcha, not just lint pedantry) -- this set is
#: that reference, with each task removing itself when done.
_background_tasks: set[asyncio.Task[None]] = set()


@app.post("/demo/{session_id}/start")
async def start_demo_session(session_id: str) -> dict[str, Any]:
    """PHASE-11 SS6/SS7: the one control the web app needs to walk all seven demo beats end to
    end -- gated on `DEMO_MODE=true` because `demo_stream.run_streamed_demo` is a scripted
    replay, not a live model session (D-015's boundary). Fires the run in the background and
    returns immediately; the browser's already-open `GET /sessions/{id}/events` stream renders
    each beat as `run_streamed_demo` produces it.
    """
    if not demo_mode():
        raise HTTPException(
            status_code=403, detail="DEMO_MODE must be true to start a streamed demo session"
        )
    if session_id in _demo_runs_in_flight:
        return {"status": "already-running"}
    orchestrator: CardinalOrchestrator = app.state.orchestrator

    async def _run() -> None:
        try:
            await demo_stream.run_streamed_demo(
                session_id,
                store=app.state.store,
                sink=orchestrator.ui_sink(session_id),
                registry=orchestrator.ui_registry(session_id),
            )
        finally:
            _demo_runs_in_flight.discard(session_id)

    _demo_runs_in_flight.add(session_id)
    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "started"}


@app.post("/mcp-apps/{session_id}/rpc")
async def mcp_app_rpc(session_id: str, request: Request) -> dict[str, Any]:
    """The *only* thing a view (via the outer iframe, PHASE-7 SS5.1) ever calls -- this route
    is what makes "the view never talks to the server directly" true rather than aspirational.
    `resources/read` goes over a real MCP-over-HTTP session to `booking-mcp`'s standalone
    transport; `tools/call` dispatches in-process into an `audience="app"` server built fresh
    for this call. Both paths are audited either way (`src/mcp/apps/proxy.py`).
    """
    body = await request.json()
    resource_uri = body.get("resourceUri")
    method = body.get("method")
    params = body.get("params") or {}
    well_formed = (
        isinstance(resource_uri, str) and isinstance(method, str) and isinstance(params, dict)
    )
    if not well_formed:
        raise HTTPException(status_code=422, detail="expected {resourceUri, method, params}")

    allowed_tools = RESOURCE_ROUTES.get(resource_uri)
    if allowed_tools is None:
        raise HTTPException(status_code=404, detail=f"no MCP App serves {resource_uri}")

    if method == "csp/violation":
        # Not a real RPC -- an App reporting that its own `securitypolicyviolation` fired
        # (gate 7.3/7.10). CSP blocks the fetch client-side, where this audit log would
        # otherwise never learn it happened; recorded as `blocked` through the same log rather
        # than a second, parallel one.
        app.state.app_audit_log.record(
            session_id=session_id,
            resource_uri=resource_uri,
            method=method,
            params=params,
            decision="blocked",
            result_status=f"client-observed CSP violation: {params.get('blockedUri')}",
        )
        return {"result": {"acknowledged": True}}

    if method == "resources/read":
        await _ensure_booking_mcp_http(app)

    try:
        result = await call_view_rpc(
            session_id=session_id,
            resource_uri=resource_uri,
            method=method,
            params=params,
            resource_server_url=BOOKING_MCP_URL,
            app_tool_config=build_booking_server(
                audience="app",
                session_id=session_id,
                store=app.state.store,
                booking_store=app.state.booking_store,
            ),
            allowed_tools=allowed_tools,
            audit=app.state.app_audit_log,
        )
    except AppRpcError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{method} failed: {exc}") from exc

    if demo_mode() and method == "tools/call" and params.get("name") == "submit_booking_draft":
        # PHASE-11 SS6's checkout beat: a human's real click just submitted the booking form
        # (the RPC above succeeded before this runs) -- react to it the way a live model would,
        # by opening checkout next. `demo_stream.on_draft_submitted` never calls
        # `confirm_booking` (CONSTITUTION I.2); it only gets the session to an opened checkout.
        #
        # Backgrounded, not awaited: this handler's own HTTP response is what the *submitting*
        # form's fetch() is waiting on, from inside the outer iframe that RPC call originated
        # in. Pushing the checkout's `mcp_app_open` SSE message before that response actually
        # reaches and is processed by the browser races React into remounting `McpAppHost` --
        # tearing down the very outer iframe this request is still in flight from -- which
        # aborts it client-side (`net::ERR_ABORTED`) before the "submitted" status the form is
        # waiting to show ever arrives. Backgrounding the task alone narrows that race without
        # closing it (the in-memory `open_checkout` path is fast enough to still win most of
        # the time); the short sleep is what actually orders "response delivered" before
        # "checkout opens" instead of leaving it to scheduling luck.
        draft_id = (params.get("arguments") or {}).get("booking_draft_id")
        if isinstance(draft_id, str):
            orchestrator: CardinalOrchestrator = app.state.orchestrator

            async def _open_checkout_after_submit(draft_id: str = draft_id) -> None:
                await asyncio.sleep(0.3)
                await demo_stream.on_draft_submitted(
                    session_id,
                    sink=orchestrator.ui_sink(session_id),
                    store=app.state.store,
                    draft_id=draft_id,
                )

            task = asyncio.create_task(_open_checkout_after_submit())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

    return {"result": result}


@app.get("/mcp-apps/{session_id}/audit")
async def mcp_app_audit(session_id: str) -> list[dict[str, Any]]:
    """Read-only view of PHASE-7 SS5.5's audit trail for one session -- what a compliance
    reviewer (or gate 7.9) would ask for after the fact, never mutated from this route.
    """
    audit: AppAuditLog = app.state.app_audit_log
    return [
        {
            "timestamp": entry.timestamp,
            "sessionId": entry.session_id,
            "resourceUri": entry.resource_uri,
            "method": entry.method,
            "paramsHash": entry.params_hash,
            "decision": entry.decision,
            "resultStatus": entry.result_status,
        }
        for entry in audit.for_session(session_id)
    ]
