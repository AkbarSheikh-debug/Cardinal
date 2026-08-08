"""Exit gate for PHASE 7 -- MCP-APPS.

    python scripts/gate_phase7.py

Needs `web/`'s npm dependencies + a Chromium build (`npm install && npx playwright install
chromium`, the same prerequisite gate 6.2 has); when they're not present this criterion set
reports `PENDING` rather than failing the whole gate, the same convention gate 1.10/3.2/4.1/6.2
use for a heavy optional prerequisite. Once it is present, as it is on this machine, every
criterion is a hard PASS/FAIL.

All ten criteria are asserted by *one* Playwright run (`web/tests/mcp-apps.spec.ts`, each test
titled `7.N ...`) against a real running `src.api.main:app` -- started here, in this process,
over `sys.executable` so it runs inside this project's own virtualenv regardless of what a bare
`python` on PATH resolves to -- plus the `booking-mcp` HTTP transport that process lazily spawns
on first use. This script's job is standing that up, running the real browser suite once, and
mapping its JSON report back onto ten separately-reported gate criteria; `web/playwright.mcp-
apps.config.ts`'s own `webServer` only brings up the built frontend, kept separate from
`playwright.config.ts` so gate 6 never pays for (or depends on) a Python backend it doesn't need.

Runs its backend on a dedicated port, not the product's :8000, and points the frontend at it via
`CARDINAL_API_PORT` (`web/vite.config.ts` reads it, defaulting to :8000 for real dev use). A
`docker compose up` left running from earlier -- a real thing that happened while building this
gate -- keeps :8000 permanently occupied; a gate that reused "whatever's already on :8000" would
silently test a stale container with none of this phase's routes instead of failing loudly.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scripts.gate_common import REPO_ROOT, Gate, Pending, python_executable, run_command

WEB_DIR = REPO_ROOT / "web"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8090
REPORT_PATH = WEB_DIR / "test-results" / "mcp-apps.json"

CRITERIA = [
    ("7.1", "Inner iframe's origin != host origin (asserted from the browser, not from config)"),
    ("7.2", "CSP on the inner document matches the resource's _meta.ui.csp, defaults applied"),
    ("7.3", "A fetch() to an undeclared domain from inside the App fails and is logged as blocked"),
    ("7.4", "ui/initialize completes; hostContext.theme reaches the App and visibly applies"),
    ("7.5", "ui/notifications/tool-input delivers pre-fill exactly once, after init"),
    ("7.6", "tools/call from the view reaches the MCP server through the host proxy only"),
    ("7.7", "ui/resource-teardown removes the iframe/listeners; no leak after 20 cycles"),
    ("7.8", "size-changed resizes the container without layout shift in the surrounding surface"),
    ("7.9", "Audit log has one entry per view-initiated RPC, no gaps, for a full booking flow"),
    ("7.10", "The App renders and functions with JavaScript's network access fully blocked"),
]


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def _start_backend() -> subprocess.Popen[bytes] | None:
    """`None` means something is already serving `:8000` (a `make dev`/`docker compose` left
    running) -- reused rather than fighting it for the port, the same live-and-let-live
    convention `--require-stack` gates use for an already-up Postgres.
    """
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
    raise RuntimeError("backend did not start listening on :8000 within 20s")


def _stop_backend(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    if sys.platform == "win32":
        # .terminate() is TerminateProcess on Windows -- no graceful shutdown delivered, so
        # this process's own ASGI lifespan (which would otherwise clean up the booking-mcp
        # subprocess it spawned) never runs. /T kills the whole tree so nothing outlives the
        # gate; discovered while building this, not a hypothetical.
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


def _run_playwright(npx: str) -> dict[str, tuple[bool, str]]:
    backend = _start_backend()
    env = {**os.environ, "CARDINAL_API_PORT": str(BACKEND_PORT)}
    try:
        result = run_command(
            [npx, "playwright", "test", "--config=playwright.mcp-apps.config.ts"],
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


def build_gate() -> Gate:
    gate = Gate(7, "MCP-APPS -- Host implementation, sandbox, booking form")

    npx = shutil.which("npx")
    playwright_bin = WEB_DIR / "node_modules" / ".bin" / "playwright"
    playwright_cmd = WEB_DIR / "node_modules" / ".bin" / "playwright.cmd"
    playwright_installed = npx is not None and (playwright_bin.exists() or playwright_cmd.exists())

    outcomes: dict[str, tuple[bool, str]] = {}
    run_error: str | None = None
    if playwright_installed:
        assert npx is not None  # playwright_installed already guarantees this
        try:
            outcomes = _run_playwright(npx)
        except Exception as exc:  # surfaced per-criterion below as a real FAIL, not swallowed
            run_error = f"{type(exc).__name__}: {exc}"

    for ident, title in CRITERIA:

        def _(ident: str = ident) -> str:
            if not playwright_installed:
                raise Pending(
                    "web/node_modules not installed -- run `npm install` and "
                    "`npx playwright install chromium` inside web/"
                )
            if run_error is not None:
                raise AssertionError(f"playwright run did not complete: {run_error}")
            if ident not in outcomes:
                raise AssertionError(f"no test titled '{ident} ...' found in the playwright report")
            passed, detail = outcomes[ident]
            assert passed, detail
            return detail

        gate.criterion(ident, title)(_)

    return gate


def main() -> int:
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
