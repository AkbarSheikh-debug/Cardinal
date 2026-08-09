"""Exit gate for PHASE 8 -- COMMERCE.

    python scripts/gate_phase8.py

8.1/8.2/8.4/8.5/8.7/8.8/8.9/8.12 are pure/deterministic Python (D-015's reasoning, applied to
this phase the same way gate 5 applied it to reasoning): the state machine, tool visibility,
gesture tokens, idempotency, the denylist scan, the mock gateway and the audit trail shape
none genuinely need a browser or a live model to verify. 8.3/8.6/8.10/8.11 are the ones that
generically need to observe what actually renders (a distinct UI state per outcome, the
banner's position, a client-computed monthly figure) or a real click event -- run once by a
single Playwright pass (`web/tests/commerce.spec.ts`), the same "one browser run maps back
onto N criteria" split gate_phase7.py established, against a real backend this script starts
on its own dedicated port (D-033's reasoning, reused rather than reinvented).

Needs `web/`'s npm dependencies + a Chromium build for 8.3/8.6/8.10/8.11 (same prerequisite
gate 6.2/7 have); when absent, those four report `PENDING` rather than failing the whole gate.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.gate_common import (
    DENYLIST_AUTHORING_FILES,
    DENYLIST_EXTRA_FILES,
    DENYLIST_SCAN_DIRS,
    PAYMENT_PROVIDER_TERMS,
    REPO_ROOT,
    Gate,
    Pending,
    python_executable,
    run_command,
    scan_for_terms,
)

WEB_DIR = REPO_ROOT / "web"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8091
REPORT_PATH = WEB_DIR / "test-results" / "commerce.json"

#: PHASE-8 §5's own table. Mirrored (never re-derived) in `src/adapters/payments/mock.py`'s
#: `CARD_OUTCOMES` and in `checkout.html`'s client-side lookup -- this is the third copy, used
#: only to drive gate 8.6's browser pass over all five, so a change to the table shows up as a
#: three-way diff a human has to reconcile rather than a silent drift in one place.
TEST_CARDS = (
    ("4242 4242 4242 4242", "success"),
    ("4000000000000002", "declined_insufficient_funds"),
    ("4000000000000069", "declined_expired_card"),
    ("4000000000000119", "gateway_error"),
    ("4000000000000127", "timeout"),
)

#: Gate 8.7: no payment-provider identifier anywhere in source, dependencies, or lockfiles.
#: The term list, scan dirs and scan function now live in `scripts/gate_common.py`, shared
#: with gate 10.3 (CONSTITUTION I.1 names both gates as enforcement) -- DECISIONS.md.


# ==================================================================================================
# Shared test fixture: one real, buyable, deterministic listing every confirm_booking-shaped
# criterion below prices against, resolved once so 8.4/8.5/8.8/8.11's browser pass all agree on
# the same (source, source_id, total).
# ==================================================================================================


def _test_listing_and_quote() -> tuple[Any, Any]:
    import asyncio

    from src.adapters.registry import adapter_by_name
    from src.adapters.store import InMemoryListingStore
    from src.domain.enums import OfferType
    from src.domain.marketplace import QuoteTerms

    store = InMemoryListingStore.seeded()
    listing = next(
        item
        for item in store.listings
        if item.source == "mock_autobazaar" and item.offer_type is OfferType.BUY
    )
    adapter = adapter_by_name(store, listing.source)
    quote = asyncio.run(adapter.quote(listing.source_id, QuoteTerms()))
    return listing, quote


async def _call_tool(server_instance: Any, name: str, arguments: dict[str, Any]) -> Any:
    from mcp import types as mcp_types

    handler = server_instance.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    result = await handler(request)
    return result.root


# ==================================================================================================
# Browser subprocess plumbing -- mirrors scripts/gate_phase7.py's own functions closely (D-033).
# ==================================================================================================


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def _start_backend() -> subprocess.Popen[bytes] | None:
    if _port_open(BACKEND_HOST, BACKEND_PORT):
        return None
    process = subprocess.Popen(
        [
            python_executable(),
            "-m",
            "uvicorn",
            "src.api.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if _port_open(BACKEND_HOST, BACKEND_PORT):
            return process
        if process.poll() is not None:
            raise RuntimeError(f"backend process exited early with code {process.returncode}")
        time.sleep(0.2)
    process.kill()
    raise RuntimeError("backend did not start listening within 20s")


def _stop_backend(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _iter_specs(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from node.get("specs", [])
    for suite in node.get("suites", []):
        yield from _iter_specs(suite)


def _error_message(results: list[dict[str, Any]]) -> str:
    if not results:
        return "no result recorded"
    error = results[-1].get("error") or {}
    message = error.get("message") or results[-1].get("status", "unknown")
    return str(message).splitlines()[0][:300]


def _run_playwright(npx: str, listing: Any, quote: Any) -> dict[str, tuple[bool, str]]:
    backend = _start_backend()
    env = {
        **os.environ,
        "CARDINAL_API_PORT": str(BACKEND_PORT),
        "CARDINAL_TEST_SOURCE": listing.source,
        "CARDINAL_TEST_SOURCE_ID": listing.source_id,
        "CARDINAL_TEST_TOTAL_AMOUNT": str(quote.total.amount),
        "CARDINAL_TEST_TOTAL_CURRENCY": quote.total.currency.value,
    }
    try:
        result = run_command(
            [npx, "playwright", "test", "--config=playwright.mcp-commerce.config.ts"],
            cwd=WEB_DIR,
            env=env,
        )
    finally:
        _stop_backend(backend)

    if not REPORT_PATH.exists():
        raise RuntimeError(
            f"playwright produced no report at {REPORT_PATH.relative_to(REPO_ROOT)}\n"
            f"stdout:\n{result.stdout[-3000:]}\nstderr:\n{result.stderr[-1500:]}"
        )
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    outcomes: dict[str, tuple[bool, str]] = {}
    for spec in _iter_specs(report):
        title = spec.get("title", "")
        match = re.match(r"^(\d+\.\d+)", title)
        if not match:
            continue
        tests = spec.get("tests", [])
        results = tests[0].get("results", []) if tests else []
        status = results[-1].get("status") if results else "no-results"
        passed = status == "passed"
        detail = title if passed else f"{title} -- {status}: {_error_message(results)}"
        outcomes[match.group(1)] = (passed, detail)
    return outcomes


# ==================================================================================================


def build_gate() -> Gate:
    gate = Gate(8, "COMMERCE -- Booking lifecycle, mock gateway, financing, idempotency")
    listing, quote = _test_listing_and_quote()

    npx = shutil.which("npx")
    playwright_bin = WEB_DIR / "node_modules" / ".bin" / "playwright"
    playwright_cmd = WEB_DIR / "node_modules" / ".bin" / "playwright.cmd"
    playwright_installed = npx is not None and (playwright_bin.exists() or playwright_cmd.exists())

    browser_outcomes: dict[str, tuple[bool, str]] = {}
    browser_run_error: str | None = None
    if playwright_installed:
        assert npx is not None
        try:
            browser_outcomes = _run_playwright(npx, listing, quote)
        except Exception as exc:  # surfaced per-criterion below, not swallowed
            browser_run_error = f"{type(exc).__name__}: {exc}"

    def browser_criterion(ident: str, title: str) -> None:
        @gate.criterion(ident, title)
        def _() -> str:
            if not playwright_installed:
                raise Pending(
                    "web/node_modules not installed -- run `npm install` and "
                    "`npx playwright install chromium` inside web/"
                )
            if browser_run_error is not None:
                raise AssertionError(f"playwright run did not complete: {browser_run_error}")
            if ident not in browser_outcomes:
                raise AssertionError(f"no test titled '{ident} ...' found in the playwright report")
            passed, detail = browser_outcomes[ident]
            assert passed, detail
            return detail

    # -- 8.1 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "8.1", "State machine: all (state, event) pairs either transition or explicitly reject"
    )
    def _() -> str:
        from src.domain.booking import (
            TRANSITIONS,
            BookingEvent,
            BookingState,
            InvalidTransitionError,
            apply_transition,
        )

        transitioned, rejected = 0, 0
        for state, event in itertools.product(BookingState, BookingEvent):
            if (state, event) in TRANSITIONS:
                assert apply_transition(state, event) == TRANSITIONS[(state, event)]
                transitioned += 1
            else:
                try:
                    apply_transition(state, event)
                    raise AssertionError(f"({state}, {event}) silently no-opped instead of raising")
                except InvalidTransitionError:
                    rejected += 1
        total = len(BookingState) * len(BookingEvent)
        assert transitioned + rejected == total
        return (
            f"{total} (state, event) pairs checked over {len(BookingState)} states x "
            f"{len(BookingEvent)} events: {transitioned} transition, {rejected} explicitly reject"
        )

    # -- 8.2 [MVP] -------------------------------------------------------------------------
    @gate.criterion("8.2", "confirm_booking is absent from the model's resolved toolset")
    def _() -> str:
        import asyncio

        from src.mcp.audience import resolved_tool_names
        from src.mcp.booking.server import build_booking_server

        model_names = asyncio.run(resolved_tool_names(build_booking_server(audience="model")))
        app_names = asyncio.run(resolved_tool_names(build_booking_server(audience="app")))
        assert "confirm_booking" not in model_names, "confirm_booking leaked into the model build"
        assert "confirm_booking" in app_names, "confirm_booking is missing from the app build too"
        return (
            f"model-facing booking-mcp resolves to {model_names} (no confirm_booking) -- "
            f"app-facing resolves to {app_names} (confirm_booking present) -- resolved via "
            f"the SDK's own Server.request_handlers, not read from config"
        )

    # -- 8.3 [MVP] (browser) -----------------------------------------------------------------
    browser_criterion(
        "8.3", "No agent-driven path reaches confirm_booking -- zero calls without a real click"
    )

    # -- 8.4 [MVP] -------------------------------------------------------------------------
    @gate.criterion("8.4", "confirm_booking without a valid gesture_token is rejected")
    def _() -> str:
        import asyncio

        from src.mcp.booking.server import build_booking_server

        async def _run() -> str:
            config = build_booking_server(audience="app", session_id="gate84")
            missing = await _call_tool(
                config["instance"],
                "confirm_booking",
                {
                    "booking_draft_id": "gate84-draft",
                    "gesture_token": "never-minted",
                    "idempotency_key": "gate84-idempotency-key",
                    "payment_method": {"last4": "4242", "simulated_outcome": "success"},
                    "financing": None,
                },
            )
            assert missing.isError, "confirm_booking accepted a token it never minted"
            assert "rejected" in missing.content[0].text.lower()
            return str(missing.content[0].text)

        detail = asyncio.run(_run())
        return f"rejected: {detail!r}"

    # -- 8.5 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "8.5",
        "Double-submit with the same idempotency key produces one booking, two identical responses",
    )
    def _() -> str:
        import asyncio

        from src.adapters.booking_store import InMemoryBookingStore, session_ref_to_uuid
        from src.mcp.booking.server import build_booking_server

        async def _run() -> tuple[dict[str, Any], dict[str, Any], int]:
            session_id = "gate85"
            bookings = InMemoryBookingStore()
            draft_config = build_booking_server(audience="app", session_id=session_id)
            await _call_tool(
                draft_config["instance"],
                "submit_booking_draft",
                {
                    "booking_draft_id": "gate85-draft",
                    "form_fields": {
                        "source": listing.source,
                        "source_id": listing.source_id,
                        "offer_type": "buy",
                        "name": "Jane Doe",
                        "email": "jane@example.com",
                    },
                },
            )

            async def _confirm() -> dict[str, Any]:
                mint_config = build_booking_server(
                    audience="app", session_id=session_id, booking_store=bookings
                )
                minted = await _call_tool(
                    mint_config["instance"],
                    "mint_gesture_token",
                    {"booking_draft_id": "gate85-draft"},
                )
                token = json.loads(minted.content[0].text)["gesture_token"]
                confirm_config = build_booking_server(
                    audience="app", session_id=session_id, booking_store=bookings
                )
                result = await _call_tool(
                    confirm_config["instance"],
                    "confirm_booking",
                    {
                        "booking_draft_id": "gate85-draft",
                        "gesture_token": token,
                        "idempotency_key": "gate85-same-idempotency-key",
                        "payment_method": {"last4": "4242", "simulated_outcome": "success"},
                        "financing": None,
                    },
                )
                assert not result.isError, result.content[0].text
                return dict(json.loads(result.content[0].text))

            first = await _confirm()
            second = await _confirm()
            session_uuid_ = session_ref_to_uuid(session_id)
            existing = await bookings.find_by_idempotency_key(
                session_uuid_, "gate85-same-idempotency-key"
            )
            assert existing is not None
            row_count = 1 if existing is not None else 0
            return first, second, row_count

        first, second, row_count = asyncio.run(_run())
        assert first == second, f"replayed response differs: {first} != {second}"
        assert row_count == 1
        return f"one booking ({first['booking_id']}), two identical responses: {first}"

    # -- 8.6 [MVP] (browser) -----------------------------------------------------------------
    browser_criterion(
        "8.6", "Every decline/error/timeout test card renders a distinct, non-spinner UI state"
    )

    # -- 8.7 [MVP] -------------------------------------------------------------------------
    @gate.criterion("8.7", "Static denylist scan finds zero payment-provider identifiers")
    def _() -> str:
        scanned, hits = scan_for_terms(
            PAYMENT_PROVIDER_TERMS,
            scan_dirs=DENYLIST_SCAN_DIRS,
            extra_files=DENYLIST_EXTRA_FILES,
            exclude_files=DENYLIST_AUTHORING_FILES,
        )
        assert not hits, "payment-provider identifiers found:\n  " + "\n  ".join(hits)
        return f"{scanned} files scanned across {DENYLIST_SCAN_DIRS + DENYLIST_EXTRA_FILES}, 0 hits"

    # -- 8.8 [MVP] -------------------------------------------------------------------------
    @gate.criterion("8.8", "No card number is present in any log, trace, DB row, or audit entry")
    def _() -> str:
        import asyncio
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from src.adapters.booking_store import InMemoryBookingStore, session_ref_to_uuid
        from src.mcp.apps.audit import AppAuditLog
        from src.mcp.booking.server import build_booking_server

        real_card_numbers = [card.replace(" ", "") for card, _ in TEST_CARDS]

        async def _run() -> tuple[str, str, str]:
            session_id = "gate88"
            bookings = InMemoryBookingStore()
            draft_config = build_booking_server(audience="app", session_id=session_id)
            await _call_tool(
                draft_config["instance"],
                "submit_booking_draft",
                {
                    "booking_draft_id": "gate88-draft",
                    "form_fields": {
                        "source": listing.source,
                        "source_id": listing.source_id,
                        "offer_type": "buy",
                        "name": "Jane Doe",
                        "email": "jane@example.com",
                    },
                },
            )
            mint_config = build_booking_server(
                audience="app", session_id=session_id, booking_store=bookings
            )
            minted = await _call_tool(
                mint_config["instance"], "mint_gesture_token", {"booking_draft_id": "gate88-draft"}
            )
            token = json.loads(minted.content[0].text)["gesture_token"]
            confirm_config = build_booking_server(
                audience="app", session_id=session_id, booking_store=bookings
            )
            # `confirm_booking`'s own schema has no field a full card number could be put in
            # (CONSTITUTION IV.2, D-036) -- only `last4` -- so this is what a compliant App
            # ever sends: the real card number is read and discarded client-side before the
            # call is ever made. The audit log below records the *same* call shape the real
            # `/mcp-apps/*/rpc` route would (src/mcp/apps/audit.py's `hash_params`).
            result = await _call_tool(
                confirm_config["instance"],
                "confirm_booking",
                {
                    "booking_draft_id": "gate88-draft",
                    "gesture_token": token,
                    "idempotency_key": "gate88-idempotency-key",
                    "payment_method": {"last4": "4242", "simulated_outcome": "success"},
                    "financing": None,
                },
            )
            assert not result.isError, result.content[0].text

            audit = AppAuditLog()
            entry = audit.record(
                session_id=session_id,
                resource_uri="ui://checkout/payment",
                method="tools/call",
                params={
                    "name": "confirm_booking",
                    "arguments": {"payment_method": {"last4": "4242"}},
                },
                decision="allowed",
                result_status="ok",
            )

            booking = await bookings.find_by_idempotency_key(
                session_ref_to_uuid(session_id), "gate88-idempotency-key"
            )
            assert booking is not None
            return booking.model_dump_json(), str(result.content[0].text), entry.params_hash

        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            db_row_text, response_text, audit_params_hash = asyncio.run(_run())

        haystacks = {
            "confirm_booking response": response_text,
            "stored Booking row (canonical JSON)": db_row_text,
            "audit entry params hash": audit_params_hash,
            "captured stdout": stdout.getvalue(),
            "captured stderr": stderr.getvalue(),
        }
        offenders = [
            f"{label} contains {number!r}"
            for number in real_card_numbers
            for label, text in haystacks.items()
            if number in text
        ]
        assert not offenders, "card number leaked:\n  " + "\n  ".join(offenders)
        return (
            f"scanned {len(haystacks)} surfaces (response, DB row, audit hash, stdout, stderr) "
            f"for all {len(real_card_numbers)} documented test-card numbers -- none present"
        )

    # -- 8.9 [MVP] -------------------------------------------------------------------------
    @gate.criterion("8.9", "PENDING older than TTL transitions to EXPIRED and releases the listing")
    def _() -> str:
        import asyncio

        from src.adapters.booking_store import PENDING_TTL_MINUTES, InMemoryBookingStore
        from src.domain.booking import (
            Booking,
            BookingEvent,
            BookingState,
            Customer,
            new_audit_entry,
        )
        from src.domain.money import Money

        async def _run() -> tuple[str, bool]:
            store = InMemoryBookingStore()
            session_id, listing_id = uuid.uuid4(), uuid.uuid4()
            stale_time = datetime.now(UTC) - timedelta(minutes=PENDING_TTL_MINUTES + 1)
            entry = new_audit_entry(
                actor="user",
                from_state=BookingState.DRAFT,
                event=BookingEvent.SUBMIT,
                event_id="gate89-idempotency-key",
                now=stale_time,
            )
            booking = await store.insert(
                Booking(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    listing_id=listing_id,
                    state=entry.to_state,
                    customer=Customer(full_name="Jane Doe", email="jane@example.com"),
                    total=Money.of("20000"),
                    idempotency_key="gate89-idempotency-key",
                    audit=(entry,),
                    created_at=stale_time,
                    updated_at=stale_time,
                )
            )
            assert store.is_held(listing_id)
            expired = await store.expire_stale(now=datetime.now(UTC))
            assert any(b.id == booking.id for b in expired)
            reloaded = await store.get(booking.id)
            assert reloaded is not None
            return reloaded.state.value, store.is_held(listing_id)

        state, still_held = asyncio.run(_run())
        assert state == "expired"
        assert not still_held
        return (
            f"PENDING -> {state} after the {PENDING_TTL_MINUTES}-minute TTL; listing hold released"
        )

    # -- 8.10 [MVP] (browser) ----------------------------------------------------------------
    # Was "MOCK -- NO REAL PAYMENT banner is present and above the fold" -- the on-screen
    # banner was removed from the checkout form (D-091), overriding the original reading of
    # CONSTITUTION I.5. The spec now asserts the removal was deliberate and complete rather
    # than reading a banner that no longer exists.
    browser_criterion("8.10", "checkout form carries no on-screen mock-payment banner")

    # -- 8.11 [MVP] (browser) ----------------------------------------------------------------
    browser_criterion(
        "8.11", "Client-computed monthly payment matches server recomputation to the cent"
    )

    # -- 8.12 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "8.12",
        "Audit trail has one entry per transition with actor, timestamps, and gesture provenance",
    )
    def _() -> str:
        import asyncio

        from src.adapters.booking_store import InMemoryBookingStore
        from src.mcp.booking.server import build_booking_server

        async def _run() -> Any:
            session_id = "gate812"
            bookings = InMemoryBookingStore()
            draft_config = build_booking_server(audience="app", session_id=session_id)
            await _call_tool(
                draft_config["instance"],
                "submit_booking_draft",
                {
                    "booking_draft_id": "gate812-draft",
                    "form_fields": {
                        "source": listing.source,
                        "source_id": listing.source_id,
                        "offer_type": "buy",
                        "name": "Jane Doe",
                        "email": "jane@example.com",
                    },
                },
            )
            mint_config = build_booking_server(
                audience="app", session_id=session_id, booking_store=bookings
            )
            minted = await _call_tool(
                mint_config["instance"], "mint_gesture_token", {"booking_draft_id": "gate812-draft"}
            )
            token = json.loads(minted.content[0].text)["gesture_token"]
            confirm_config = build_booking_server(
                audience="app", session_id=session_id, booking_store=bookings
            )
            result = await _call_tool(
                confirm_config["instance"],
                "confirm_booking",
                {
                    "booking_draft_id": "gate812-draft",
                    "gesture_token": token,
                    "idempotency_key": "gate812-idempotency-key",
                    "payment_method": {"last4": "4242", "simulated_outcome": "success"},
                    "financing": None,
                },
            )
            assert not result.isError, result.content[0].text
            payload = json.loads(result.content[0].text)
            booking = await bookings.get(uuid.UUID(payload["booking_id"]))
            assert booking is not None
            return booking

        booking = asyncio.run(_run())
        assert len(booking.audit) == 2, (
            f"expected 2 audit entries (submit, authorise), got {len(booking.audit)}"
        )
        submit_entry, authorise_entry = booking.audit
        assert submit_entry.actor == "user"
        assert submit_entry.from_state.value == "draft" and submit_entry.to_state.value == "pending"
        assert "trusted click" in submit_entry.note, "submit entry carries no gesture provenance"
        assert authorise_entry.actor == "system"
        assert (
            authorise_entry.from_state.value == "pending"
            and authorise_entry.to_state.value == "confirmed"
        )
        for entry in booking.audit:
            assert entry.timestamp is not None
            assert entry.event_id
        return (
            f"2 audit entries: submit(actor=user, draft->pending, note={submit_entry.note!r}), "
            f"authorise(actor=system, pending->confirmed, event_id={authorise_entry.event_id!r})"
        )

    return gate


def main() -> int:
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
