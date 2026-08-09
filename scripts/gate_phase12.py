"""Exit gate for PHASE 12 -- IDENTITY (PLAN-02 P12).

    python scripts/gate_phase12.py                  # 12.5 is PENDING with no Postgres running
    python scripts/gate_phase12.py --require-stack  # 12.5 must genuinely pass

12.2 needs `web/node_modules` + Chromium and reports PENDING without them, the same
convention gate 6.2 established for a heavy optional prerequisite. Everything else is pure
Python against the real FastAPI app through `TestClient`, which is the same in-memory path
`DEMO_MODE` takes (D-015's reasoning: a gate that needs a live model proves less, not more).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.gate_common import (
    REPO_ROOT,
    Gate,
    Pending,
    python_executable,
    run_command,
    scan_for_terms,
)
from src.adapters.db.session import ENV_DATABASE_URL
from src.domain.identity import DEMO_AUTH_BANNER, DEMO_OTP_CODES, IncomeBand

WEB = REPO_ROOT / "web"

#: A dedicated port, not :8000 -- D-033's reasoning, and the specific trap `web/vite.config.ts`
#: records: a `docker compose up` left running from earlier in the day is still bound to :8000,
#: so a gate that assumes "something on :8000 must be mine" silently tests a stale container.
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8123

#: Scrubbed for the same reason gate 11.4 scrubs (CONSTITUTION III.7): 12.2 has to prove the
#: login works with the environment unset, not that it works on a machine where Postgres
#: happens to be configured.
_APP_ENV_VARS = (
    "CARDINAL_DATABASE_URL",
    "CARDINAL_BOOKING_MCP_URL",
    "ANTHROPIC_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
)


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


#: CONSTITUTION I.1's posture applied to auth (PLAN-02 §0.2): a demo build must not carry a
#: JWT library, an auth-provider SDK, or a signing secret. The whole point of an opaque
#: server-side token is that there is nothing to forge offline and nothing to leak from the
#: repository -- and the way that stops being true is someone adding `pyjwt` "just to try".
AUTH_DENYLIST_TERMS: tuple[str, ...] = (
    "pyjwt",
    "python-jose",
    "jsonwebtoken",
    "passlib",
    "bcrypt",
    "argon2",
    "auth0",
    "okta",
    "firebase-auth",
    "next-auth",
    # Signing-secret *shapes*, deliberately not a bare `SECRET_KEY`: `LANGFUSE_SECRET_KEY`
    # is a legitimate third-party API credential P9 reads from the environment, and it is
    # neither a JWT library nor a signing secret this codebase mints tokens with. Exactly
    # the carve-out CONSTITUTION I.3 makes for "BMW" as a brand name versus a BMW Group
    # endpoint, and D-044 makes for the payment denylist -- scan for the thing, not a
    # substring that happens to appear inside the thing's innocent neighbours.
    "JWT_SECRET",
    "AUTH_SECRET",
    "SESSION_SECRET",
    "TOKEN_SECRET",
    "SIGNING_KEY",
)

#: This file spells the denylist out literally, so it is excluded from its own scan -- the
#: same carve-out `DENYLIST_AUTHORING_FILES` makes for gates 8.7/10.3. Both lockfiles are in
#: scope: a transitive JWT dependency is exactly as much of a problem as a direct one.
AUTH_SCAN_DIRS = ("src", "scripts")
AUTH_EXTRA_FILES = (
    "pyproject.toml",
    "web/package.json",
    "web/package-lock.json",
)

BUYER = {
    "email": "gate12-buyer@example.com",
    "role": "buyer",
    "code": "123456",
    "full_name": "Gate Buyer",
    "phone": "+49 170 1234567",
    "profile": {"city": "Berlin", "country": "DE"},
}
SELLER = {
    "email": "gate12-seller@example.com",
    "role": "seller",
    "code": "234567",
    "full_name": "Gate Seller",
    "phone": "+49 170 7654321",
    "profile": {"role_title": "Sales Manager"},
}


def _sign_in(client: TestClient, body: dict[str, object]) -> dict:
    client.post("/auth/request-otp", json={"email": body["email"], "role": body["role"]})
    response = client.post("/auth/verify-otp", json=body)
    assert response.status_code == 200, f"sign-in failed: {response.status_code} {response.text}"
    return response.json()


@contextmanager
def memory_backend() -> Iterator[None]:
    """Run a `TestClient` criterion against the in-memory store, whatever the environment says.

    Two reasons, and the second is the load-bearing one:

    1. **These criteria are about transport and authorisation, not persistence.** 12.1/12.4/
       12.8/12.10 assert what a route returns for a given caller. Which store sits behind it
       is 12.5's question, and 12.5 asks it directly against real Postgres through
       `run_async`. Letting the environment decide the backend for the other four would make
       them fail for a reason unrelated to what they check.

    2. **On native Windows they cannot run against Postgres at all.** `TestClient` drives the
       app on a `ProactorEventLoop`, and psycopg's async mode refuses that loop outright --
       the same interaction PROGRESS.md already records for gate 8 and that
       `src/adapters/db/session.py`'s `run_async` exists to work around for CLI entry points.
       A gate that goes red on Windows for an event-loop mismatch is a gate nobody trusts.
    """
    saved = os.environ.pop(ENV_DATABASE_URL, None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ[ENV_DATABASE_URL] = saved


def build_gate(*, require_stack: bool) -> Gate:
    gate = Gate(12, "IDENTITY -- accounts, roles, dummy OTP, profile capture")

    # -- 12.1 [MVP] ---------------------------------------------------------------
    @gate.criterion(
        "12.1", "each demo OTP code authenticates a seeded account; a fourth code is rejected"
    )
    def _() -> str:
        from src.api.main import app

        accepted: list[str] = []
        with memory_backend(), TestClient(app) as client:
            for index, code in enumerate(DEMO_OTP_CODES):
                email = f"gate121-{index}@example.com"
                client.post("/auth/request-otp", json={"email": email, "role": "buyer"})
                response = client.post(
                    "/auth/verify-otp",
                    json={**BUYER, "email": email, "code": code},
                )
                assert response.status_code == 200, f"code {code} was refused: {response.text}"
                accepted.append(code)

            client.post(
                "/auth/request-otp", json={"email": "gate121-x@example.com", "role": "buyer"}
            )
            refused = client.post(
                "/auth/verify-otp",
                json={**BUYER, "email": "gate121-x@example.com", "code": "999999"},
            )
            assert refused.status_code == 401, (
                f"a non-demo code was accepted with {refused.status_code}"
            )
        return f"accepted {accepted}; rejected '999999' with 401"

    # -- 12.2 [MVP] ---------------------------------------------------------------
    # Was "demo-auth banner above the fold on /login" -- the on-screen banner was removed
    # (D-091) at the product owner's request. The disclosure it carried is still true and
    # still returned by the API (12.10); this criterion now covers what is left of its own
    # substance, the browser-driven sign-in flow itself.
    @gate.criterion("12.2", "full sign-in works in a browser, no on-screen demo banner")
    def _() -> str:
        npx = shutil.which("npx")
        playwright_installed = (WEB / "node_modules" / ".bin" / "playwright").exists() or (
            WEB / "node_modules" / ".bin" / "playwright.cmd"
        ).exists()
        if npx is None or not playwright_installed:
            raise Pending(
                "web/node_modules not installed -- run `npm install` and "
                "`npx playwright install chromium` inside web/, then re-run"
            )

        env = _scrubbed_demo_env()
        backend = _start_backend(env)
        try:
            result = run_command(
                [npx, "playwright", "test", "--config=playwright.auth.config.ts"],
                cwd=WEB,
                env=env,
            )
        finally:
            _stop_backend(backend)

        report = WEB / "test-results" / "auth.json"
        stats = {}
        if report.exists():
            stats = json.loads(report.read_text(encoding="utf-8")).get("stats", {})
        assert result.returncode == 0, (
            f"playwright exited {result.returncode}\n{result.stdout[-2000:]}\n"
            f"{result.stderr[-1000:]}"
        )
        return (
            f"web/tests/auth.spec.ts passed against a real Chromium and a scrubbed-env "
            f"backend on :{BACKEND_PORT} -- stats="
            f"{ {k: stats.get(k) for k in ('expected', 'unexpected', 'flaky', 'skipped')} }"
        )

    # -- 12.3 [MVP] ---------------------------------------------------------------
    @gate.criterion("12.3", "denylist scan: zero JWT libs, auth-provider SDKs or signing secrets")
    def _() -> str:
        scanned, hits = scan_for_terms(
            AUTH_DENYLIST_TERMS,
            scan_dirs=AUTH_SCAN_DIRS,
            extra_files=AUTH_EXTRA_FILES,
            exclude_files=(Path(__file__).resolve(),),
        )
        assert not hits, "auth denylist hits:\n  " + "\n  ".join(hits)
        return (
            f"{scanned} files scanned across {AUTH_SCAN_DIRS + AUTH_EXTRA_FILES} for "
            f"{len(AUTH_DENYLIST_TERMS)} JWT/auth-provider/secret terms, 0 hits"
        )

    # -- 12.4 [MVP] ---------------------------------------------------------------
    @gate.criterion("12.4", "a buyer token cannot read a seller route; 403 not an accidental 404")
    def _() -> str:
        from src.api.main import app

        with memory_backend(), TestClient(app) as client:
            _sign_in(client, SELLER)
            allowed = client.get("/seller/profile")
            assert allowed.status_code == 200, f"seller was refused: {allowed.status_code}"

            client.cookies.clear()
            _sign_in(client, BUYER)
            denied = client.get("/seller/profile")
            assert denied.status_code == 403, (
                f"buyer got {denied.status_code} on a seller route (expected 403)"
            )

            client.cookies.clear()
            anonymous = client.get("/seller/profile")
            assert anonymous.status_code == 401, (
                f"anonymous got {anonymous.status_code} (expected 401)"
            )
        return "seller=200, buyer=403, anonymous=401 on GET /seller/profile"

    # -- 12.5 [MVP] ---------------------------------------------------------------
    @gate.criterion("12.5", "account + profile survive process restart, every field intact")
    def _() -> str:
        database_url = os.environ.get(ENV_DATABASE_URL)
        if not database_url:
            if require_stack:
                raise AssertionError(f"{ENV_DATABASE_URL} unset and --require-stack passed")
            raise Pending(
                f"{ENV_DATABASE_URL} unset -- start Postgres (`docker compose up -d postgres`), "
                "then re-run with --require-stack"
            )

        from src.adapters.db.identity_store import PostgresAccountStore
        from src.adapters.db.session import run_async, session_factory
        from src.domain.identity import AccountRole
        from src.domain.money import Money

        email = f"gate125-{uuid.uuid4().hex[:12]}@example.com"

        async def round_trip() -> tuple[str, str, str]:
            written = PostgresAccountStore(session_factory())
            await written.request_otp(email=email, role=AccountRole.BUYER)
            account, token, _ = await written.verify_otp(
                email=email,
                role=AccountRole.BUYER,
                code="123456",
                full_name="Gate Restart",
                phone="+49 170 1234567",
                profile_fields={
                    "city": "Hamburg",
                    "country": "DE",
                    "customer_type": "corporate",
                    "annual_income": {"amount": "88000", "currency": "EUR"},
                },
            )
            # A fresh store over a fresh sessionmaker stands in for a restarted process --
            # the same substitution gates 3.2/4.1 already make.
            reread = PostgresAccountStore(session_factory())
            resumed = await reread.find_account(email=email, role=AccountRole.BUYER)
            assert resumed is not None, "account did not survive the round trip"
            assert resumed.id == account.id
            assert resumed.full_name == "Gate Restart"

            profile = await reread.get_buyer_profile(account.id)
            assert profile is not None, "profile did not survive the round trip"
            assert profile.annual_income == Money.of("88000"), (
                f"exact income drifted to {profile.annual_income}"
            )
            assert profile.income_band is IncomeBand.FROM_50K
            assert profile.customer_type.value == "corporate"

            live = await reread.resolve_token(token.token)
            assert live is not None, "token did not survive the round trip"
            return str(resumed.id), str(profile.annual_income), profile.income_band.value

        account_id, income, band = run_async(round_trip())
        return (
            f"account {account_id[:8]}..., profile and token all reloaded through a fresh "
            f"store instance; exact income {income} intact, band derived as {band!r}"
        )

    # -- 12.6 [MVP] ---------------------------------------------------------------
    @gate.criterion(
        "12.6", "annual_income, income_band and phone are absent from every exported span"
    )
    def _() -> str:
        from src.agent.tracing import (
            clear_captured_spans,
            configure_tracing,
            get_captured_spans,
            get_tracer,
        )

        configure_tracing()
        clear_captured_spans()

        raw_phone = "+49 170 1234567"
        raw_income = "88000"
        with get_tracer().start_as_current_span("gate126.signup") as span:
            span.set_attribute("account.phone", raw_phone)
            span.set_attribute("account.email", "gate126@example.com")
            span.set_attribute("profile.annual_income", raw_income)
            span.set_attribute("profile.income_band", IncomeBand.FROM_50K.value)
            span.set_attribute("profile.employer", "Acme GmbH")
            span.set_attribute("tool.name", "signup")

        spans = [s for s in get_captured_spans() if s.name == "gate126.signup"]
        assert spans, "the span never reached the in-memory exporter"
        attributes = dict(spans[0].attributes or {})
        blob = json.dumps({k: str(v) for k, v in attributes.items()})

        for needle, label in ((raw_phone, "phone"), (raw_income, "income"), ("Acme", "employer")):
            assert needle not in blob, f"raw {label} survived into an exported span"
        markers = [k for k, v in attributes.items() if isinstance(v, str) and "redacted" in v]
        assert len(markers) >= 5, f"expected every PII attribute redacted, got {markers}"
        # Redaction keeps shapes, not just removes values (CONSTITUTION IV.1).
        assert attributes["tool.name"] == "signup", "a non-PII attribute was wrongly scrubbed"
        return (
            f"{len(attributes)} attributes exported, {len(markers)} redaction markers "
            f"({sorted(markers)}); raw phone/income/employer absent, tool.name untouched"
        )

    # -- 12.7 [MVP] ---------------------------------------------------------------
    @gate.criterion(
        "12.7", "annual_income, income_band and employer reach zero model-facing payloads"
    )
    def _() -> str:
        """Structural, not behavioural: `src/agent` and `src/mcp` are every module that can
        build something the model sees. If neither mentions these field names, no prompt or
        tool result can carry them -- which is a stronger statement than watching one session
        not happen to include them (the same reasoning D-046 applies to gate 10.1).
        """
        sensitive = ("annual_income", "income_band", "employer")
        offenders: list[str] = []
        scanned = 0
        for package in ("agent", "mcp"):
            for path in sorted((REPO_ROOT / "src" / package).rglob("*.py")):
                scanned += 1
                text = path.read_text(encoding="utf-8")
                # `ast` rather than a substring scan so a field name inside a comment
                # explaining *why* it is absent doesn't fail the criterion it documents.
                tree = ast.parse(text, filename=str(path))
                literals = {
                    node.value
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
                for field in sensitive:
                    if field in literals or field in names:
                        offenders.append(f"{path.relative_to(REPO_ROOT)}: {field}")

        prompts = sorted((REPO_ROOT / "prompts").glob("*.md"))
        for path in prompts:
            body = path.read_text(encoding="utf-8")
            scanned += 1
            for field in sensitive:
                if field in body:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {field}")

        assert not offenders, "sensitive fields reachable by the model:\n  " + "\n  ".join(
            offenders
        )
        return (
            f"{scanned} files scanned (src/agent, src/mcp, prompts/) for {list(sensitive)}; "
            "0 references -- no prompt or tool result can carry them"
        )

    # -- 12.8 [MVP] ---------------------------------------------------------------
    @gate.criterion("12.8", "income_band is derived; no route can set it independently")
    def _() -> str:
        from src.api.main import app

        with memory_backend(), TestClient(app) as client:
            _sign_in(
                client,
                {
                    **BUYER,
                    "email": "gate128@example.com",
                    "profile": {
                        "city": "Berlin",
                        "country": "DE",
                        "annual_income": None,
                        "income_band": IncomeBand.OVER_100K.value,
                    },
                },
            )
            claimed = client.get("/auth/me").json()["profile"]
            assert claimed["income_band"] == IncomeBand.UNDISCLOSED.value, (
                f"a crafted band was honoured: {claimed['income_band']}"
            )

            client.cookies.clear()
            _sign_in(
                client,
                {
                    **BUYER,
                    "email": "gate128b@example.com",
                    "profile": {
                        "city": "Berlin",
                        "country": "DE",
                        "annual_income": {"amount": "120000", "currency": "EUR"},
                        "income_band": IncomeBand.UNDER_25K.value,
                    },
                },
            )
            derived = client.get("/auth/me").json()["profile"]
            assert derived["income_band"] == IncomeBand.OVER_100K.value, (
                f"the band was not derived from the figure: {derived['income_band']}"
            )
        return (
            "a body claiming '100k_plus' with no income resolved to 'undisclosed'; a body "
            "claiming 'under_25k' with EUR 120000 resolved to '100k_plus' -- derived, "
            "never accepted"
        )

    # -- 12.9 [MVP] ---------------------------------------------------------------
    @gate.criterion(
        "12.9", "DEMO_MODE=true completes a login with no signup and no ANTHROPIC_API_KEY"
    )
    def _() -> str:
        saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        saved_db = os.environ.pop(ENV_DATABASE_URL, None)
        os.environ["DEMO_MODE"] = "true"
        try:
            from src.api.main import app, build_account_store, demo_mode

            assert demo_mode(), "DEMO_MODE did not take effect"
            store = build_account_store("memory")
            assert type(store).__name__ == "InMemoryAccountStore", (
                f"DEMO_MODE resolved to {type(store).__name__}, not the in-memory store"
            )
            with TestClient(app) as client:
                body = _sign_in(client, {**BUYER, "email": "gate129@example.com"})
                assert body["created"] is True
                me = client.get("/auth/me")
                assert me.status_code == 200
                role = me.json()["account"]["role"]
        finally:
            os.environ.pop("DEMO_MODE", None)
            if saved_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved_key
            if saved_db is not None:
                os.environ[ENV_DATABASE_URL] = saved_db
        return (
            f"signed in and read /auth/me (role={role!r}) with DEMO_MODE=true, "
            "ANTHROPIC_API_KEY and CARDINAL_DATABASE_URL both unset"
        )

    # -- 12.10 [MVP] --------------------------------------------------------------
    @gate.criterion("12.10", "request-otp is honest about being a mock: banner + codes")
    def _() -> str:
        from src.api.main import app

        with memory_backend(), TestClient(app) as client:
            body = client.post(
                "/auth/request-otp", json={"email": "gate1210@example.com", "role": "buyer"}
            ).json()
        assert body["demo_codes"] == list(DEMO_OTP_CODES), (
            f"demo codes drifted from the documented three: {body['demo_codes']}"
        )
        assert body["banner"] == DEMO_AUTH_BANNER
        assert "NOT REAL SECURITY" in body["banner"]
        return f"banner={body['banner']!r}, demo_codes={body['demo_codes']}"

    # -- 12.11 [SCALE] ------------------------------------------------------------
    @gate.criterion("12.11", "[SCALE] OTP attempt rate limiting")
    def _() -> str:
        raise Pending(
            "rate limiting on OTP attempts not built -- [SCALE] (PLAN-02 P12); the demo "
            "codes are public by design, so throttling guesses protects nothing yet"
        )

    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-stack",
        action="store_true",
        help="fail criterion 12.5 instead of reporting it PENDING when no database is configured",
    )
    args = parser.parse_args(argv)
    return build_gate(require_stack=args.require_stack).run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
