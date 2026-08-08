"""Exit gate for PHASE 11 -- DELIVERY.

    python -m scripts.gate_phase11

Unlike every other gate, part of this one is *meant* to be run by a human on a different
machine (PHASE-11 SS7's own text) -- 11.8 always reports PENDING with instructions rather than
a script pretending to be that person. Everything else runs for real when its prerequisite is
present, PENDING when it isn't, the same convention gate 1.10/6.2/7 use for a heavy or
optional dependency:

- 11.1/11.2/11.5/11.6 need Docker running -- `docker compose build && up -d`, real containers,
  real `docker inspect`.
- 11.3/11.4 need `web/node_modules` + a Chromium build (gate 6.2/7's own prerequisite) -- a
  disposable backend on its own port, launched with an environment scrubbed to just
  `DEMO_MODE=true`, driving `web/tests/demo-e2e.spec.ts` for real.
- 11.7/11.9/11.10 are pure filesystem/subprocess checks, always run.
- 11.8 is always PENDING (a human, a different machine, by definition).
- 11.11 is `[SCALE]`, always PENDING (no public deployment exists).
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
from pathlib import Path
from typing import Any

import yaml

from scripts.gate_common import REPO_ROOT, Gate, Pending, python_executable, run_command

WEB_DIR = REPO_ROOT / "web"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8092
DEMO_REPORT_PATH = WEB_DIR / "test-results" / "demo-e2e.json"

MAX_IMAGE_BYTES = 800 * 1024 * 1024


# ---------------------------------------------------------------------------------------------
# 11.1/11.2/11.5/11.6 -- real Docker
# ---------------------------------------------------------------------------------------------


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = run_command(["docker", "info"])
    return result.returncode == 0


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return run_command(["docker", "compose", *args])


def _compose_ps() -> list[dict[str, Any]]:
    result = _compose("ps", "--format", "json")
    if not result.stdout.strip():
        return []
    # `docker compose ps --format json` emits one JSON object per line, not a JSON array.
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _wait_for_healthy(service_names: set[str], *, timeout_s: float = 120.0) -> dict[str, str]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, str] = {}
    while time.monotonic() < deadline:
        rows = _compose_ps()
        last = {row["Service"]: row.get("Health", "") or row.get("State", "") for row in rows}
        seen = set(last)
        if service_names <= seen and all(last[name] in {"healthy"} for name in service_names):
            return last
        time.sleep(2)
    return last


_docker_state: dict[str, Any] = {"built": False, "up": False, "health": {}}


def _ensure_stack_up() -> dict[str, str]:
    """Builds and starts the real compose stack once per gate run; every 11.1/11.2/11.5/11.6
    criterion that needs it shares this one build+up rather than each paying for its own.
    """
    if _docker_state["up"]:
        return _docker_state["health"]
    build = _compose("build")
    if build.returncode != 0:
        raise AssertionError(
            f"docker compose build failed:\n{build.stdout[-2000:]}\n{build.stderr[-2000:]}"
        )
    _docker_state["built"] = True
    up = _compose("up", "-d")
    if up.returncode != 0:
        raise AssertionError(f"docker compose up failed:\n{up.stdout[-2000:]}\n{up.stderr[-2000:]}")
    health = _wait_for_healthy({"postgres", "booking", "api", "web"}, timeout_s=120.0)
    _docker_state["up"] = True
    _docker_state["health"] = health
    return health


def check_11_1() -> str:
    if not _docker_available():
        raise Pending("Docker not installed or the daemon is not reachable (`docker info` failed)")
    health = _ensure_stack_up()
    unhealthy = {name: state for name, state in health.items() if state != "healthy"}
    assert not unhealthy, f"not all services became healthy within 120s: {unhealthy}"
    return f"all 4 services healthy within 120s: {health}"


def check_11_2() -> str:
    if not _docker_available():
        raise Pending("Docker not installed or the daemon is not reachable")
    _ensure_stack_up()
    import urllib.request

    with urllib.request.urlopen("http://localhost:8000/health", timeout=10) as resp:
        body = json.loads(resp.read())
    assert body.get("status") == "ok", f"unexpected /health body: {body}"
    listings = body.get("listings", 0)
    assert listings >= 100, f"expected >=100 listings, got {listings}"
    return f"/health -> {body}"


def check_11_5() -> str:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose.get("services", {})
    assert "booking" in services, "docker-compose.yml has no 'booking' service"
    assert "web" in services, "docker-compose.yml has no 'web' service"
    booking, web = services["booking"], services["web"]
    assert booking != web, "'booking' and 'web' are the same service definition"
    booking_cmd = " ".join(booking.get("command", []))
    assert "src.mcp.booking.http" in booking_cmd, (
        f"'booking' service command does not run booking-mcp's HTTP transport: {booking_cmd!r}"
    )
    web_context = (web.get("build") or {}).get("context")
    assert web_context == "./web", (
        f"'web' service does not build from its own context: {web_context!r}"
    )
    assert "ports" not in booking, (
        "'booking' publishes a host port -- it should only be reachable from 'api' over the "
        "compose network (CONSTITUTION II.5)"
    )
    return (
        "'booking' (src.mcp.booking.http, no published port) and 'web' (builds ./web/Dockerfile) "
        "are distinct compose services, each its own hostname on the compose network"
    )


def _image_for_service(service: str) -> str:
    result = _compose("images", "-q", service)
    image_id = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    assert image_id, f"no image id for service {service!r}: {result.stdout!r} {result.stderr!r}"
    return image_id


def check_11_6() -> str:
    if not _docker_available():
        raise Pending("Docker not installed or the daemon is not reachable")
    _ensure_stack_up()
    lines: list[str] = []
    for service in ("api", "booking", "web"):
        image_id = _image_for_service(service)
        user = run_command(
            ["docker", "inspect", "--format", "{{.Config.User}}", image_id]
        ).stdout.strip()
        size_raw = run_command(
            ["docker", "inspect", "--format", "{{.Size}}", image_id]
        ).stdout.strip()
        size = int(size_raw or "0")
        assert user and user not in {"0", "root"}, f"{service} image runs as root (User={user!r})"
        assert size <= MAX_IMAGE_BYTES, (
            f"{service} image is {size / 1_000_000:.0f} MB (limit 800 MB)"
        )
        lines.append(f"{service}: user={user!r} size={size / 1_000_000:.0f}MB")
    return "; ".join(lines)


# ---------------------------------------------------------------------------------------------
# 11.3/11.4 -- Playwright e2e, disposable backend, DEMO_MODE-only environment
# ---------------------------------------------------------------------------------------------


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


#: CONSTITUTION III.7 / gate 11.4: every app-relevant variable this project reads is explicitly
#: removed before the backend is launched, and only `DEMO_MODE=true` is added back -- proving
#: the demo path works with the environment unset, not merely that it works on this machine
#: where a database happens to be configured.
_APP_ENV_VARS = (
    "CARDINAL_DATABASE_URL",
    "CARDINAL_BOOKING_MCP_URL",
    "ANTHROPIC_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
)


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


def _run_demo_playwright(npx: str) -> tuple[bool, str]:
    env = _scrubbed_demo_env()
    backend = _start_backend(env)
    try:
        result = run_command(
            [npx, "playwright", "test", "--config=playwright.demo.config.ts"], cwd=WEB_DIR, env=env
        )
    finally:
        _stop_backend(backend)

    if not DEMO_REPORT_PATH.exists():
        return False, (
            f"playwright produced no report at {DEMO_REPORT_PATH.relative_to(REPO_ROOT)}\n"
            f"stdout:\n{result.stdout[-3000:]}\nstderr:\n{result.stderr[-1500:]}"
        )
    report = json.loads(DEMO_REPORT_PATH.read_text(encoding="utf-8"))
    stats = report.get("stats", {})
    passed = stats.get("unexpected", 1) == 0 and stats.get("expected", 0) > 0
    detail = f"stats={stats}"
    if not passed:
        specs = report.get("suites", [])
        detail += f"\n{json.dumps(specs)[:2000]}"
    return passed, detail


_demo_e2e_cache: dict[str, Any] = {}


def _demo_e2e_outcome() -> tuple[bool, str]:
    if "outcome" not in _demo_e2e_cache:
        npx = shutil.which("npx")
        playwright_bin = WEB_DIR / "node_modules" / ".bin" / "playwright"
        playwright_cmd = WEB_DIR / "node_modules" / ".bin" / "playwright.cmd"
        installed = npx is not None and (playwright_bin.exists() or playwright_cmd.exists())
        if not installed:
            _demo_e2e_cache["outcome"] = None
        else:
            assert npx is not None
            _demo_e2e_cache["outcome"] = _run_demo_playwright(npx)
    return _demo_e2e_cache["outcome"]


def check_11_3() -> str:
    outcome = _demo_e2e_outcome()
    if outcome is None:
        raise Pending(
            "web/node_modules not installed -- run `npm install` and "
            "`npx playwright install chromium` inside web/"
        )
    passed, detail = outcome
    assert passed, f"demo-e2e.spec.ts did not pass: {detail}"
    return f"web/tests/demo-e2e.spec.ts walked all seven beats and screenshotted each -- {detail}"


def check_11_4() -> str:
    outcome = _demo_e2e_outcome()
    if outcome is None:
        raise Pending(
            "web/node_modules not installed -- run `npm install` and "
            "`npx playwright install chromium` inside web/"
        )
    passed, detail = outcome
    assert passed, f"demo-e2e.spec.ts did not pass under a scrubbed environment: {detail}"
    scrubbed = ", ".join(_APP_ENV_VARS)
    return f"backend launched with {{{scrubbed}}} removed and only DEMO_MODE=true set -- {detail}"


# ---------------------------------------------------------------------------------------------
# 11.7 -- .env.example covers every variable the codebase reads
# ---------------------------------------------------------------------------------------------

#: Scoped to product code, not gate/test tooling -- the same kind of documented scan-scope
#: decision `scripts/gate_common.py`'s denylist scan already makes (DECISIONS.md D-044).
#: `scripts/`, `tests/` and `web/tests`/`web/playwright*.config.ts` set their own disposable
#: `CARDINAL_TEST_*`/`CARDINAL_API_PORT` env vars for a gate's own spawned subprocess -- those
#: are gate-internal wiring a deployer never sets, not application configuration.
#:
#: Most call sites don't pass a literal to `os.environ` directly -- `ENV_DATABASE_URL =
#: "CARDINAL_DATABASE_URL"` then `os.environ.get(ENV_DATABASE_URL)` a few lines later -- so this
#: resolves through a same-file `NAME = "VALUE"` constant table rather than only matching an
#: inline string literal.
_ASSIGNMENT_PATTERN = re.compile(r"(\w+)\s*=\s*[\"'](\w+)[\"']")
_PY_ENV_CALL_PATTERN = re.compile(r"os\.environ(?:\.get)?\(\s*(?:[\"'](\w+)[\"']|(\w+))")
_PY_ENV_IN_PATTERN = re.compile(r"(?:[\"'](\w+)[\"']|(\w+))\s+in\s+os\.environ\b")
_TS_ENV_PATTERN = re.compile(r"process\.env\.(\w+)")


def _read_env_vars_from(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".py":
        return set(_TS_ENV_PATTERN.findall(text))

    constants = dict(_ASSIGNMENT_PATTERN.findall(text))
    found: set[str] = set()
    for pattern in (_PY_ENV_CALL_PATTERN, _PY_ENV_IN_PATTERN):
        for literal, identifier in pattern.findall(text):
            if literal:
                found.add(literal)
            elif identifier in constants:
                found.add(constants[identifier])
    return found


def check_11_7() -> str:
    found: set[str] = set()
    for path in (REPO_ROOT / "src").rglob("*.py"):
        found |= _read_env_vars_from(path)
    for path in (WEB_DIR / "src").rglob("*.ts*"):
        found |= _read_env_vars_from(path)
    found |= _read_env_vars_from(WEB_DIR / "vite.config.ts")
    # ANTHROPIC_API_KEY is read by the Claude Agent SDK itself, not by an `os.environ` call
    # anywhere in this repository's own source -- undetectable by this scan by construction,
    # documented here rather than silently missing from the coverage this criterion proves.
    found.add("ANTHROPIC_API_KEY")

    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", example, re.MULTILINE))

    missing = found - documented
    assert not missing, f".env.example is missing: {sorted(missing)}"
    return (
        f"{len(found)} variable(s) read in src/ + web/src/ + vite.config.ts, "
        f"all in .env.example: {sorted(found)}"
    )


# ---------------------------------------------------------------------------------------------
# 11.9 -- deck + video under docs/
# ---------------------------------------------------------------------------------------------

_DECK_EXTENSIONS = (".pptx", ".pdf", ".key")
_VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv")


def check_11_9() -> str:
    docs_dir = REPO_ROOT / "docs"
    deck = [p for p in docs_dir.glob("*") if p.suffix.lower() in _DECK_EXTENSIONS]
    video = [p for p in docs_dir.rglob("*") if p.suffix.lower() in _VIDEO_EXTENSIONS]
    if deck and video:
        return f"deck: {deck[0].name}; video: {video[0].name}"
    if deck and not video:
        raise Pending(
            f"deck present ({deck[0].name}); video not recorded -- "
            "see docs/VIDEO-SCRIPT.md for the shot list, recorded against DEMO_MODE per "
            "web/tests/demo-e2e.spec.ts's own seven beats"
        )
    raise Pending("neither a deck nor a recorded video exists under docs/ yet")


# ---------------------------------------------------------------------------------------------
# 11.10 -- every other gate exits 0
# ---------------------------------------------------------------------------------------------


def check_11_10() -> str:
    results = []
    for phase in range(0, 11):
        result = run_command([python_executable(), "-m", f"scripts.gate_phase{phase}"])
        results.append((phase, result.returncode))
    failed = [phase for phase, code in results if code != 0]
    assert not failed, f"gate(s) {failed} exited non-zero"
    return f"gates 0..10 each exit 0 ({len(results)} gates checked; gate 11 is this run itself)"


# ---------------------------------------------------------------------------------------------


def build_gate() -> Gate:
    gate = Gate(11, "DELIVERY -- Docker, deploy, CI/CD, docs, demo assets")

    gate.criterion("11.1", "Clean clone -> docker compose up -> all services healthy within 120s")(
        check_11_1
    )
    gate.criterion("11.2", "Seed runs automatically; /health reports >=100 listings")(check_11_2)
    gate.criterion("11.3", "Playwright e2e walks all seven beats and screenshots each")(check_11_3)
    gate.criterion("11.4", "e2e passes with the entire environment unset except DEMO_MODE=true")(
        check_11_4
    )
    gate.criterion("11.5", "'booking' service resolves on a distinct hostname from 'web'")(
        check_11_5
    )
    gate.criterion("11.6", "Every image runs as non-root; no image exceeds 800 MB")(check_11_6)
    gate.criterion(
        "11.7", ".env.example covers every variable read anywhere in the codebase (scan asserts)"
    )(check_11_7)

    @gate.criterion("11.8", "README's run instructions executed verbatim on a clean machine")
    def _() -> str:
        raise Pending(
            "by definition a human, on a machine that has never seen this repo, following "
            "README.md's 'Run it' section verbatim -- nothing this script runs can stand in "
            "for that. See README.md's Run it section."
        )

    gate.criterion("11.9", "Deck and video present under docs/")(check_11_9)
    gate.criterion("11.10", "make verify green: every gate 0-11")(check_11_10)

    @gate.criterion("11.11", "[SCALE] Public deployment reachable and healthy")
    def _() -> str:
        raise Pending("no public deployment exists -- PHASE-11 SS2 marks this [SCALE]")

    return gate


def main() -> int:
    try:
        return build_gate().run()
    finally:
        if _docker_state["up"]:
            print(
                "\n(docker compose stack left running for inspection -- "
                "`docker compose down` to stop it, data volume untouched)"
            )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
