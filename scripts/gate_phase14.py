"""Exit gate for PHASE 14 -- CART (PLAN-02 P14).

    python scripts/gate_phase14.py

Two halves, the split D-015 established. 14.6/14.8/14.9/14.11 and the server side of 14.10 are
pure Python -- static scans and the real FastAPI app through `TestClient`, no model, no key.
14.1/14.2/14.3/14.4/14.5/14.7/14.12 and the *rendering* side of 14.10 need a browser: they
assert what actually renders and what a real click does, which is not a thing source code can
be read for. Those run `web/tests/cart.spec.ts` against a backend this script starts itself,
on its own port, with the environment scrubbed to `DEMO_MODE=true` -- the pattern gates
7/8/11/12 already use, and 14.12's own evidence besides.

Without `web/node_modules` + Chromium the browser criteria report PENDING rather than FAIL,
the convention gate 6.2 established for a heavy optional prerequisite.
"""

from __future__ import annotations

import argparse
import ast
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
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient

from scripts.gate_common import REPO_ROOT, Gate, Pending, python_executable, run_command
from src.adapters.catalogue.dealers import generate_dealers
from src.adapters.catalogue.generator import SOURCES, generate_catalogue
from src.adapters.db.session import ENV_DATABASE_URL

WEB = REPO_ROOT / "web"
REPORT_PATH = WEB / "test-results" / "cart.json"

#: Its own port, distinct from gate 12's :8123 and gate 7/8/11's -- D-033's reasoning: a
#: `docker compose up` left running from earlier in the day is still bound to :8000, and two
#: gates sharing a port would make either one's failure look like the other's.
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8124

_APP_ENV_VARS = (
    "CARDINAL_DATABASE_URL",
    "CARDINAL_BOOKING_MCP_URL",
    "ANTHROPIC_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
)

BUYER = {
    "email": "gate14-buyer@example.com",
    "role": "buyer",
    "code": "123456",
    "full_name": "Gate 14 Buyer",
    "phone": "+49 170 1234567",
    "profile": {"city": "Berlin", "country": "DE"},
}
OTHER_BUYER = {**BUYER, "email": "gate14-other@example.com", "full_name": "Gate 14 Other"}


# -- backend lifecycle (gates 7/8/11/12's shape) ---------------------------------------------


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def _scrubbed_demo_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _APP_ENV_VARS}
    env["DEMO_MODE"] = "true"
    env["CARDINAL_API_PORT"] = str(BACKEND_PORT)
    return env


def _start_backend(env: dict[str, str]) -> subprocess.Popen[bytes]:
    if _port_open(BACKEND_HOST, BACKEND_PORT):
        raise RuntimeError(f"something is already listening on :{BACKEND_PORT}")
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
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if _port_open(BACKEND_HOST, BACKEND_PORT):
            return process
        if process.poll() is not None:
            raise RuntimeError(f"backend exited early with code {process.returncode}")
        time.sleep(0.2)
    process.kill()
    raise RuntimeError(f"backend did not start listening on :{BACKEND_PORT} within 20s")


def _stop_backend(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@contextmanager
def memory_backend() -> Iterator[None]:
    """In-memory regardless of the environment -- `test_api_cart.py`'s own note, and the same
    `ProactorEventLoop`/psycopg interaction gate 12 records: a gate that goes red on Windows
    for an event-loop mismatch is a gate nobody trusts."""
    saved = os.environ.pop(ENV_DATABASE_URL, None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ[ENV_DATABASE_URL] = saved


# -- fixtures shared by both halves ----------------------------------------------------------


def _listing_pair() -> tuple[Any, Any]:
    """One listing whose dealer is verified and one whose dealer is not, out of the real
    generated catalogue -- so 14.5 renders both branches of the payee disclosure against real
    data rather than a hand-written pair that could drift from what the generator produces."""
    catalogue = generate_catalogue()
    dealers = {d.id: d for d in generate_dealers(42, SOURCES)}

    def _pick(*, verified: bool) -> Any:
        return next(
            x
            for x in catalogue
            if x.dealer_id is not None
            and x.offer_type.is_buyable
            and x.is_available
            and dealers[x.dealer_id].is_verified is verified
        )

    return _pick(verified=True), _pick(verified=False)


def _sign_in(client: TestClient, body: dict[str, Any]) -> None:
    client.post("/auth/request-otp", json={"email": body["email"], "role": body["role"]})
    verified = client.post("/auth/verify-otp", json=body)
    assert verified.status_code == 200, f"sign-in failed: {verified.text}"


def _buyable(client: TestClient) -> Any:
    for listing in client.app.state.store.listings:  # type: ignore[attr-defined]
        if listing.offer_type.is_buyable and listing.is_available:
            return listing
    raise AssertionError("no buyable listing in the catalogue")


def _strip_ts_comments(source: str) -> str:
    """Comments out of a `.ts`/`.tsx` file, so gate 14.6 scans code and not prose.

    Deliberately conservative rather than a parser: block comments go, and a line goes only
    when its first non-whitespace characters are `//` or `*`. A trailing `// ...` after real
    code stays, which is the safe direction -- this scan's job is to never miss a call, and
    over-keeping text can only produce a false alarm somebody reads, while over-stripping
    could hide one.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith(("//", "*"))
    )


async def _call_tool(server_instance: Any, name: str, arguments: dict[str, Any]) -> Any:
    """The SDK's own dispatch, the way gate 8 calls it -- not this project's bookkeeping read
    back to itself (D-012's reasoning, reused)."""
    from mcp import types as mcp_types

    handler = server_instance.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    result = await handler(request)
    return result.root


# -- the browser half ------------------------------------------------------------------------


def _iter_specs(report: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for suite in report.get("suites", []):
        yield from suite.get("specs", [])
        for nested in suite.get("suites", []):
            yield from nested.get("specs", [])


def _error_message(results: list[dict[str, Any]]) -> str:
    for result in reversed(results):
        for error in result.get("errors", []):
            message = str(error.get("message", "")).strip().splitlines()
            if message:
                return message[0][:300]
    return "no error message in the report"


def _run_playwright(npx: str) -> dict[str, tuple[bool, str]]:
    verified, unverified = _listing_pair()
    env = _scrubbed_demo_env()
    env |= {
        "CARDINAL_TEST_VERIFIED_SOURCE": verified.source,
        "CARDINAL_TEST_VERIFIED_SOURCE_ID": verified.source_id,
        "CARDINAL_TEST_UNVERIFIED_SOURCE": unverified.source,
        "CARDINAL_TEST_UNVERIFIED_SOURCE_ID": unverified.source_id,
    }
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()

    backend = _start_backend(env)
    try:
        result = run_command(
            [npx, "playwright", "test", "--config=playwright.cart.config.ts"],
            cwd=WEB,
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


# ============================================================================================


def build_gate() -> Gate:
    gate = Gate(14, "CART -- add to cart, payee disclosure, checkout on /cart")

    npx = shutil.which("npx")
    playwright_installed = npx is not None and (
        (WEB / "node_modules" / ".bin" / "playwright").exists()
        or (WEB / "node_modules" / ".bin" / "playwright.cmd").exists()
    )

    browser_outcomes: dict[str, tuple[bool, str]] = {}
    browser_run_error: str | None = None
    if playwright_installed:
        assert npx is not None
        try:
            browser_outcomes = _run_playwright(npx)
        except Exception as exc:  # surfaced per-criterion below, never swallowed
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

    # -- 14.1 [MVP] (browser) ----------------------------------------------------------------
    browser_criterion(
        "14.1", "add-to-cart from a real CarCard click reaches the cart; the badge updates"
    )

    # -- 14.2 [MVP] (browser) ----------------------------------------------------------------
    browser_criterion(
        "14.2", "/cart mounts the same ui://checkout/payment resource -- read from the DOM"
    )

    # -- 14.3 [MVP] (browser) ----------------------------------------------------------------
    browser_criterion("14.3", "the chat rail is mounted and live on /cart, same session")

    # -- 14.4 [MVP] (browser) ----------------------------------------------------------------
    browser_criterion(
        "14.4", "payee legal name, address and phone above the fold and above the pay control"
    )

    # -- 14.5 [MVP] (browser) ----------------------------------------------------------------
    browser_criterion("14.5", "an unverified payee is flagged explicitly; a verified one is not")

    # -- 14.6 [MVP] --------------------------------------------------------------------------
    @gate.criterion(
        "14.6", "exactly one code path reaches confirm_booking, and it is the gesture-gated one"
    )
    def _() -> str:
        """Four facts, which together are what "exactly one path" means here.

        Comments and docstrings are excluded by parsing rather than by grepping: this repo
        deliberately *discusses* `confirm_booking` all over the place (CONSTITUTION I.2 is its
        whole trust story), and a plain text scan would drown in prose while missing a real
        call written as `getattr(mod, "confirm_" + "booking")`.
        """
        registrations: list[str] = []
        code_references: list[str] = []
        for path in sorted((REPO_ROOT / "src").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for node in ast.walk(tree):
                # `@tool("confirm_booking", ...)` -- the one registration.
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    first = node.args[0] if node.args else None
                    if (
                        node.func.id == "tool"
                        and isinstance(first, ast.Constant)
                        and first.value == "confirm_booking"
                    ):
                        registrations.append(f"{rel}:{node.lineno}")
                # Any *executable* mention: a def, a name, or a string literal that is not a
                # docstring. `ast` never yields comments, so those are excluded for free.
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    if node.name == "confirm_booking":
                        code_references.append(f"{rel}:{node.lineno}")
                elif isinstance(node, ast.Name) and node.id == "confirm_booking":
                    code_references.append(f"{rel}:{node.lineno}")
                elif isinstance(node, ast.Constant) and node.value == "confirm_booking":
                    code_references.append(f"{rel}:{node.lineno}")

        assert len(registrations) == 1, f"expected one @tool registration, found {registrations}"
        assert registrations[0].startswith("src/mcp/booking/tools.py"), registrations

        # The only two modules allowed to name it as an exact literal: the tool module that
        # defines it, and the proxy allowlist that decides which view may call it. (Note what
        # this deliberately does *not* catch: `src/domain/trust.py` embeds the name inside a
        # larger regex, so it is not an exact `ast.Constant` match. That is correct -- a
        # detector pattern mentioning a tool is not a path to it -- but it is also the shape a
        # real evasion would take, which is why the browser criterion 14.7 exists alongside
        # this one rather than instead of it.)
        allowed_modules = {
            "src/mcp/booking/tools.py",
            "src/mcp/booking/resources.py",
        }
        strays = [r for r in code_references if r.rsplit(":", 1)[0] not in allowed_modules]
        assert not strays, "named in code outside the one path:\n  " + "\n  ".join(strays)

        # The handler consumes a gesture token before it does anything else. Asserted by
        # position, not by presence: a token checked *after* the payment call would satisfy
        # "the handler mentions a gesture token" while gating nothing.
        source = (REPO_ROOT / "src" / "mcp" / "booking" / "tools.py").read_text(encoding="utf-8")
        body = source.split("async def confirm_booking", 1)[1].split("\nasync def ", 1)[0]
        assert "gesture_tokens.consume" in body, "confirm_booking does not consume a gesture token"
        statements = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and not line.strip().startswith(("#", '"""', "'''", ")", "]"))
        ]
        # Skip the signature's own continuation lines, then take the first real statement.
        gesture_line = next(
            i for i, line in enumerate(statements) if "gesture_tokens.consume" in line
        )
        assert gesture_line <= 3, (
            f"the gesture check is statement {gesture_line} of confirm_booking, not the first: "
            + " | ".join(statements[: gesture_line + 1])
        )

        # And the browser's only route to it is the host proxy, whose allowlist names it.
        from src.mcp.booking.resources import ALLOWED_VIEW_TOOLS, CHECKOUT_URI

        callers = [uri for uri, tools in ALLOWED_VIEW_TOOLS.items() if "confirm_booking" in tools]
        assert callers == [CHECKOUT_URI], f"more than the checkout view may call it: {callers}"

        # The host page never names it in code -- it cannot call it directly, only the
        # sandboxed App can, and only through the proxy. Comments are stripped first, the same
        # exclusion the Python half gets for free from `ast`: this repo's whole trust story is
        # *about* `confirm_booking`, and the modules nearest it are the ones most likely to
        # explain in prose why they never touch it. A scan that cannot tell an explanation
        # from a call would either fail on good documentation or push people to stop writing
        # it, and the second outcome is worse than no scan at all.
        web_files = sorted((WEB / "src").rglob("*.ts*"))
        web_hits = [
            str(p.relative_to(REPO_ROOT)).replace("\\", "/")
            for p in web_files
            if "confirm_booking" in _strip_ts_comments(p.read_text(encoding="utf-8"))
        ]
        assert not web_hits, f"the host page names confirm_booking in code: {web_hits}"

        return (
            f"1 @tool registration ({registrations[0]}); code references confined to "
            f"{sorted(allowed_modules)}; the gesture token is consumed at statement "
            f"{gesture_line} of confirm_booking ({statements[gesture_line][:60]}...); "
            f"ALLOWED_VIEW_TOOLS grants it to {CHECKOUT_URI} only; "
            f"0 code references across {len(web_files)} files in web/src"
        )

    # -- 14.7 [MVP] (browser) ----------------------------------------------------------------
    browser_criterion(
        "14.7", "no agent-driven path adds to cart or opens checkout -- zero, without a click"
    )

    # -- 14.8 [MVP] --------------------------------------------------------------------------
    @gate.criterion("14.8", "gates 8.3 / 8.6 / 8.10 / 8.11 still green -- in-chat checkout intact")
    def _() -> str:
        """Run, not read (CONSTITUTION III.1). Gate 8's four browser criteria are the ones
        `/cart` could plausibly have regressed -- they drive the *in-chat* mount, which P14 is
        an addition to and never a migration from (PLAN-02 §0.1).
        """
        result = subprocess.run(
            [python_executable(), "-m", "scripts.gate_phase8"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        wanted = ("8.3", "8.6", "8.10", "8.11")
        statuses: dict[str, str] = {}
        for line in result.stdout.splitlines():
            match = re.match(r"\s+(\d+\.\d+)\s+(PASS|FAIL|PENDING)\b", line)
            if match and match.group(1) in wanted:
                statuses[match.group(1)] = match.group(2)

        missing = [c for c in wanted if c not in statuses]
        assert not missing, f"gate 8 reported nothing for {missing}\n{result.stdout[-2000:]}"
        if all(statuses[c] == "PENDING" for c in wanted):
            raise Pending("gate 8's browser criteria are PENDING -- web/node_modules not installed")
        failed = [f"{c}={statuses[c]}" for c in wanted if statuses[c] != "PASS"]
        assert not failed, f"gate 8 regressed: {', '.join(failed)}"
        assert result.returncode == 0, f"gate 8 exited {result.returncode}"
        return (
            "scripts.gate_phase8 exits 0 -- "
            + ", ".join(f"{c} {statuses[c]}" for c in wanted)
            + " (re-run in full, not read)"
        )

    # -- 14.9 [MVP] --------------------------------------------------------------------------
    @gate.criterion(
        "14.9", "double-submit from /cart with one idempotency key: one booking, two responses"
    )
    def _() -> str:
        """The draft is created the way `/cart` creates one -- `POST /cart/checkout` opens the
        booking form, the form's own submit becomes the draft -- rather than hand-built, so
        this asserts idempotency on the path the cart actually takes rather than on a
        lookalike.
        """
        import asyncio

        from src.adapters.booking_store import InMemoryBookingStore, session_ref_to_uuid
        from src.mcp.booking.server import build_booking_server

        session_id = f"gate14-{uuid.uuid4().hex[:8]}"
        idempotency_key = "gate14-same-idempotency-key"

        with memory_backend():
            from src.api.main import app

            with TestClient(app) as client:
                _sign_in(client, BUYER)
                listing = _buyable(client)
                added = client.post(
                    "/cart/items",
                    json={
                        "source": listing.source,
                        "source_id": listing.source_id,
                        "offer_type": "buy",
                    },
                )
                assert added.status_code == 200, added.text
                item_id = added.json()["items"][0]["item_id"]

                opened = client.post(
                    "/cart/checkout", json={"session_id": session_id, "item_id": item_id}
                )
                assert opened.status_code == 200, opened.text
                assert opened.json()["resource_uri"] == "ui://booking/form"

        draft_id = f"{session_id}-draft"
        bookings = InMemoryBookingStore()

        async def _run() -> tuple[dict[str, Any], dict[str, Any], int]:
            await _call_tool(
                build_booking_server(audience="app", session_id=session_id)["instance"],
                "submit_booking_draft",
                {
                    "booking_draft_id": draft_id,
                    "form_fields": {
                        "source": listing.source,
                        "source_id": listing.source_id,
                        "offer_type": "buy",
                        "name": BUYER["full_name"],
                        "email": BUYER["email"],
                    },
                },
            )

            async def _confirm() -> dict[str, Any]:
                minted = await _call_tool(
                    build_booking_server(
                        audience="app", session_id=session_id, booking_store=bookings
                    )["instance"],
                    "mint_gesture_token",
                    {"booking_draft_id": draft_id},
                )
                token = json.loads(minted.content[0].text)["gesture_token"]
                confirmed = await _call_tool(
                    build_booking_server(
                        audience="app", session_id=session_id, booking_store=bookings
                    )["instance"],
                    "confirm_booking",
                    {
                        "booking_draft_id": draft_id,
                        "gesture_token": token,
                        "idempotency_key": idempotency_key,
                        "payment_method": {"last4": "4242", "simulated_outcome": "success"},
                        "financing": None,
                    },
                )
                assert not confirmed.isError, confirmed.content[0].text
                return dict(json.loads(confirmed.content[0].text))

            first = await _confirm()
            second = await _confirm()
            existing = await bookings.find_by_idempotency_key(
                session_ref_to_uuid(session_id), idempotency_key
            )
            return first, second, 1 if existing is not None else 0

        first, second, rows = asyncio.run(_run())
        assert first == second, f"replayed response differs: {first} != {second}"
        assert rows == 1, "the idempotency key did not resolve to exactly one booking"
        return (
            f"cart -> /cart/checkout -> ui://booking/form -> one booking "
            f"({first['booking_id']}), two identical responses under key {idempotency_key!r}"
        )

    # -- 14.10 [MVP] (server half here, rendering half in the browser) ------------------------
    @gate.criterion("14.10", "a withdrawn cart line reports unavailable and is refused at checkout")
    def _() -> str:
        with memory_backend():
            from src.api.main import app

            with TestClient(app) as client:
                _sign_in(client, BUYER)
                listing = _buyable(client)
                added = client.post(
                    "/cart/items",
                    json={
                        "source": listing.source,
                        "source_id": listing.source_id,
                        "offer_type": "buy",
                    },
                )
                assert added.status_code == 200, added.text
                item_id = added.json()["items"][0]["item_id"]
                assert added.json()["items"][0]["available"] is True

                # Withdrawn *after* the add -- which is the only way a cart can hold one, since
                # `POST /cart/items` refuses an unavailable listing at the door. This is why
                # the browser cannot produce this state on demand and asserts the rendering
                # against the payload below instead (`cart.spec.ts`'s 14.10).
                store = client.app.state.store  # type: ignore[attr-defined]
                withdrawn = listing.model_copy(update={"withdrawn_at": listing.fetched_at})
                store._by_key[listing.natural_key] = withdrawn

                reread = client.get("/cart/items").json()["items"][0]
                assert reread["available"] is False, "a withdrawn line still reports available"

                refused = client.post(
                    "/cart/checkout",
                    json={"session_id": "gate14-withdrawn", "item_id": item_id},
                )
                assert refused.status_code == 409, (
                    f"checkout on a withdrawn listing returned {refused.status_code}"
                )
                detail = refused.json()["detail"]

        browser = browser_outcomes.get("14.10")
        rendered = (
            "rendering PENDING (no browser)"
            if not playwright_installed
            else ("rendering PASS" if browser and browser[0] else f"rendering FAILED: {browser}")
        )
        if playwright_installed and browser_run_error is None:
            assert browser is not None and browser[0], f"the rendered state failed: {browser}"
        return (
            f"available flipped true -> false on withdrawal; POST /cart/checkout -> 409 "
            f"{detail!r}; {rendered}"
        )

    # -- 14.11 [MVP] -------------------------------------------------------------------------
    @gate.criterion("14.11", "cart is account-scoped: account A's token never reads account B's")
    def _() -> str:
        with memory_backend():
            from src.api.main import app

            with TestClient(app) as first, TestClient(app) as second:
                _sign_in(first, BUYER)
                listing = _buyable(first)
                added = first.post(
                    "/cart/items",
                    json={
                        "source": listing.source,
                        "source_id": listing.source_id,
                        "offer_type": "buy",
                    },
                )
                assert added.status_code == 200, added.text
                item_id = added.json()["items"][0]["item_id"]

                _sign_in(second, OTHER_BUYER)
                theirs = second.get("/cart/items")
                assert theirs.status_code == 200
                assert theirs.json()["count"] == 0, "account B can see account A's cart"

                # The item id is not a capability either: `CartStore` resolves an id *within*
                # an account, so a leaked one buys nothing.
                second.delete(f"/cart/items/{item_id}")
                second.post("/cart/checkout", json={"session_id": "gate14-x", "item_id": item_id})
                assert first.get("/cart/items").json()["count"] == 1, "B mutated A's cart"

                anonymous = TestClient(app)
                assert anonymous.get("/cart/items").status_code == 401

        # And the shape that makes it structural rather than checked: no route takes an id.
        from src.api.cart import router as cart_router

        paths = {getattr(route, "path", "") for route in cart_router.routes}
        assert not any("account" in path for path in paths), paths
        return (
            f"A=1 item, B reads 0; B's DELETE and checkout on A's item_id changed nothing; "
            f"anonymous=401; no cart route takes an account id ({sorted(paths)})"
        )

    # -- 14.12 [MVP] (browser) ---------------------------------------------------------------
    browser_criterion(
        "14.12", "DEMO_MODE walks add-to-cart -> /cart -> mock pay with the environment unset"
    )

    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Exit gate for PHASE 14 -- CART")
    parser.parse_args()
    return build_gate().run()


if __name__ == "__main__":
    raise SystemExit(main())
