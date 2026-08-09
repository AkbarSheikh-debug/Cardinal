"""Exit gate for PHASE 15 -- SELLER CONSOLE (PLAN-02 P15).

    python scripts/gate_phase15.py

Two halves, the split D-015 established. 15.1/15.2/15.3/15.5/15.7/15.9 are pure Python --
the scorer is a pure function and the routes run through the real FastAPI app via
`TestClient`, no model, no key. 15.4/15.6/15.8/15.10 need a browser: an SSE stream reaching a
*rendered* console, and tier phrasing asserted on what a dealer actually reads. Those run
`web/tests/seller.spec.ts` against a backend this script starts itself, on its own port, with
the environment scrubbed to `DEMO_MODE=true` -- which is also 15.10's own evidence.

Without `web/node_modules` + Chromium the browser criteria report PENDING rather than FAIL,
the convention gate 6.2 established.

**15.9 asserts a stronger property than PLAN-02 §P15 asked for**, and deliberately: the plan
lists income band as a scoring signal and asks that `undisclosed` carry no hidden penalty.
Income is not an input at all here (D-079), so the criterion checks that no band -- disclosed,
undisclosed or absent -- can reach or move a lead score, which is the same guarantee with
nothing left to reason about.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from scripts.gate_common import REPO_ROOT, Gate, Pending, python_executable, run_command
from src.adapters.db.session import ENV_DATABASE_URL
from src.domain.identity import IncomeBand
from src.domain.lead import LeadEvent
from src.domain.lead_scoring import score_lead

WEB = REPO_ROOT / "web"
REPORT_PATH = WEB / "test-results" / "seller.json"

#: Its own port again -- distinct from gate 12's :8123 and gate 14's :8124 (D-033).
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8125

_APP_ENV_VARS = (
    "CARDINAL_DATABASE_URL",
    "CARDINAL_BOOKING_MCP_URL",
    "ANTHROPIC_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
)

BUYER: dict[str, Any] = {
    "email": "gate15-buyer@example.com",
    "role": "buyer",
    "code": "123456",
    "full_name": "Gate 15 Buyer",
    "phone": "+49 170 1234567",
    "profile": {
        "city": "Berlin",
        "country": "DE",
        # Present on purpose: a privacy assertion about a buyer with no income on file
        # proves nothing.
        "annual_income": {"amount": "88000", "currency": "EUR"},
        "employer": "Contoso GmbH",
    },
}
OTHER_BUYER = {**BUYER, "email": "gate15-buyer-2@example.com", "full_name": "Other Buyer"}


# -- backend lifecycle (gates 7/8/11/12/14's shape) -------------------------------------------


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
    """In-memory regardless of the environment -- the same reasoning gates 12 and 14 record,
    including the Windows `ProactorEventLoop`/psycopg interaction."""
    saved = os.environ.pop(ENV_DATABASE_URL, None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ[ENV_DATABASE_URL] = saved


# -- shared helpers ---------------------------------------------------------------------------


def _sign_in(client: TestClient, body: dict[str, Any]) -> None:
    client.post("/auth/request-otp", json={"email": body["email"], "role": body["role"]})
    verified = client.post("/auth/verify-otp", json=body)
    assert verified.status_code == 200, f"sign-in failed: {verified.text}"


def _sign_in_seller(client: TestClient, dealer_id: str, email: str) -> None:
    _sign_in(
        client,
        {
            "email": email,
            "role": "seller",
            "code": "234567",
            "full_name": "Gate 15 Seller",
            "phone": "+49 170 7654321",
            "profile": {"role_title": "Sales Manager", "dealer_id": dealer_id},
        },
    )


def _listing_with_dealer(client: TestClient, *, dealer_not: str | None = None) -> Any:
    for listing in client.app.state.store.listings:  # type: ignore[attr-defined]
        if not (listing.offer_type.is_buyable and listing.is_available and listing.dealer_id):
            continue
        if dealer_not is not None and str(listing.dealer_id) == dealer_not:
            continue
        return listing
    raise AssertionError("no buyable listing with a dealer in the catalogue")


def _add_to_cart(client: TestClient, listing: Any) -> dict[str, Any]:
    response = client.post(
        "/cart/items",
        json={"source": listing.source, "source_id": listing.source_id, "offer_type": "buy"},
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _browser_fixture() -> tuple[str, str, str]:
    """The car the browser half's buyer will engage with, and the dealership that owns it --
    resolved from the real generated catalogue rather than guessed, so the seller signs in as
    the dealer who should actually receive the lead."""
    from src.adapters.catalogue.generator import generate_catalogue

    for listing in generate_catalogue():
        if listing.offer_type.is_buyable and listing.is_available and listing.dealer_id:
            return str(listing.dealer_id), listing.source, listing.source_id
    raise AssertionError("no buyable listing with a dealer in the generated catalogue")


# -- the browser half -------------------------------------------------------------------------


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
    dealer_id, source, source_id = _browser_fixture()
    env = _scrubbed_demo_env()
    env |= {
        "CARDINAL_TEST_DEALER_ID": dealer_id,
        "CARDINAL_TEST_SOURCE": source,
        "CARDINAL_TEST_SOURCE_ID": source_id,
    }
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()

    backend = _start_backend(env)
    try:
        result = run_command(
            [npx, "playwright", "test", "--config=playwright.seller.config.ts"],
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


# =============================================================================================


def build_gate() -> Gate:
    gate = Gate(15, "SELLER CONSOLE -- lead routing, intent tiers, privacy")

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

    # -- 15.1 [MVP] ---------------------------------------------------------------------------
    @gate.criterion(
        "15.1", "every qualifying action produces exactly one Lead, routed to the car's dealer"
    )
    def _() -> str:
        with memory_backend():
            from src.api.main import app

            with TestClient(app) as buyer, TestClient(app) as seller:
                listing = _listing_with_dealer(buyer)
                _sign_in(buyer, BUYER)
                added = _add_to_cart(buyer, listing)
                _sign_in_seller(seller, str(listing.dealer_id), "gate151-seller@example.com")

                after_add = seller.get("/seller/leads").json()["leads"]
                assert len(after_add) == 1, f"a cart-add produced {len(after_add)} leads"

                # The second and third qualifying actions land on the *same* lead.
                buyer.post(
                    "/cart/checkout",
                    json={"session_id": "gate151", "item_id": added["items"][0]["item_id"]},
                )
                # And a repeat of the first changes nothing about the count.
                _add_to_cart(buyer, listing)

                leads = seller.get("/seller/leads").json()["leads"]
                assert len(leads) == 1, f"three actions produced {len(leads)} leads"
                events = set(leads[0]["events"])
                assert events == {"cart_add", "checkout_opened"}, events

                # A second car from the same dealer is a second lead -- two conversations.
                second_car = next(
                    x
                    for x in buyer.app.state.store.listings  # type: ignore[attr-defined]
                    if x.dealer_id == listing.dealer_id
                    and x.source_id != listing.source_id
                    and x.offer_type.is_buyable
                    and x.is_available
                )
                _add_to_cart(buyer, second_car)
                assert len(seller.get("/seller/leads").json()["leads"]) == 2

                routed = {lead["source_id"] for lead in seller.get("/seller/leads").json()["leads"]}
        return (
            f"3 actions on one car -> 1 lead carrying {sorted(events)}; a second car -> a "
            f"second lead; both routed to the dealer that owns them ({sorted(routed)})"
        )

    # -- 15.2 [MVP] ---------------------------------------------------------------------------
    @gate.criterion("15.2", "the tier is deterministic: same signals, same tier and score, twice")
    def _() -> str:
        kwargs: dict[str, Any] = {
            "events": (LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED),
            "target_date": date(2026, 8, 20),
            "today": date(2026, 8, 9),
            "budget": Decimal("28000"),
            "price": Decimal("26500"),
            "return_sessions": 2,
            "is_corporate": True,
        }
        first, second = score_lead(**kwargs), score_lead(**kwargs)
        assert first == second, "two identical calls produced different scores"
        assert first.model_dump_json() == second.model_dump_json()

        # Event order must not matter: a lead records *which* actions happened, and the store
        # can observe them in either order depending on which request landed first.
        reordered = score_lead(**{**kwargs, "events": tuple(reversed(kwargs["events"]))})
        assert reordered.score == first.score, "event order changed the score"

        # And the module is held to gate 5.9's bar -- stdlib and pydantic only.
        import ast

        from src.domain import lead_scoring

        tree = ast.parse(inspect.getsource(lead_scoring))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        allowed = {"__future__", "datetime", "decimal", "src", "pydantic", "enum", "typing"}
        assert roots <= allowed, f"lead_scoring imports outside the allowed set: {roots - allowed}"

        return (
            f"score={first.score:.6f} tier={first.tier.value} byte-identical across two runs; "
            f"event order irrelevant; imports {sorted(roots)} all stdlib/pydantic/domain"
        )

    # -- 15.3 [MVP] ---------------------------------------------------------------------------
    @gate.criterion(
        "15.3", "every tier traces to named signals whose contributions sum to the score (1e-9)"
    )
    def _() -> str:
        checked = 0
        worst = 0.0
        for events in (
            (LeadEvent.CART_ADD,),
            (LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED),
            (LeadEvent.CART_ADD, LeadEvent.CHECKOUT_OPENED, LeadEvent.BOOKING_SUBMITTED),
        ):
            for target in (None, date(2026, 8, 11), date(2026, 10, 1), date(2027, 6, 1)):
                for budget, price in (
                    (None, None),
                    (Decimal("30000"), Decimal("24000")),
                    (Decimal("20000"), Decimal("29000")),
                ):
                    result = score_lead(
                        events=events,
                        target_date=target,
                        today=date(2026, 8, 9),
                        budget=budget,
                        price=price,
                    )
                    drift = abs(result.score - sum(s.contribution for s in result.signals))
                    worst = max(worst, drift)
                    assert drift < 1e-9, f"contributions do not sum to the score: {drift}"
                    assert all(s.explanation.strip() for s in result.signals), (
                        "a signal reached the panel with no sentence attached"
                    )
                    for signal in result.signals:
                        assert abs(signal.contribution - signal.weight * signal.value) < 1e-9
                    checked += 1
        return (
            f"{checked} lead shapes checked across 3 event sets x 4 target dates x 3 budget "
            f"cases; worst |score - sum(contributions)| = {worst:.2e}; every signal named, "
            f"weighted and explained"
        )

    # -- 15.4 [MVP] (browser) -----------------------------------------------------------------
    browser_criterion("15.4", "a new lead reaches an open /seller/events stream, no reload")

    # -- 15.5 [MVP] ---------------------------------------------------------------------------
    @gate.criterion(
        "15.5", "seller A never sees seller B's leads -- scoped inside the query, not after it"
    )
    def _() -> str:
        with memory_backend():
            from src.api.main import app

            with TestClient(app) as buyer, TestClient(app) as mine, TestClient(app) as theirs:
                listing = _listing_with_dealer(buyer)
                other = _listing_with_dealer(buyer, dealer_not=str(listing.dealer_id))
                _sign_in(buyer, BUYER)
                _add_to_cart(buyer, listing)

                _sign_in_seller(mine, str(listing.dealer_id), "gate155-mine@example.com")
                _sign_in_seller(theirs, str(other.dealer_id), "gate155-theirs@example.com")

                mine_leads = mine.get("/seller/leads").json()["leads"]
                theirs_leads = theirs.get("/seller/leads").json()["leads"]
                assert len(mine_leads) == 1 and theirs_leads == []

                # A leaked lead id buys nothing: the lookup is scoped, not filtered.
                lead_id = mine_leads[0]["id"]
                stolen = theirs.post(f"/seller/leads/{lead_id}/contacted")
                assert stolen.status_code == 404, f"another dealer got {stolen.status_code}"
                assert mine.get("/seller/leads").json()["leads"][0]["state"] == "new"

                anonymous = TestClient(app)
                assert anonymous.get("/seller/leads").status_code == 401

        # And the shape that makes it structural: no seller route takes a dealer id.
        from src.api.seller import router as seller_router

        paths = {getattr(route, "path", "") for route in seller_router.routes}
        assert not any("dealer_id" in path for path in paths), paths
        assert "/seller" not in paths, "a bare /seller API route would collide with the page"

        # `LeadStore`'s own surface: every read requires a dealer id, and there is no "all".
        from src.adapters.lead_store import LeadStore

        for name in ("for_dealer", "get", "set_state"):
            parameters = inspect.signature(getattr(LeadStore, name)).parameters
            assert "dealer_id" in parameters, f"LeadStore.{name} is not dealer-scoped"

        return (
            f"A=1 lead, B reads 0; B's POST on A's lead id -> 404 and changed nothing; "
            f"anonymous -> 401; no seller route takes a dealer id ({sorted(paths)}); every "
            f"LeadStore read requires one"
        )

    # -- 15.6 [MVP] (browser) -----------------------------------------------------------------
    browser_criterion("15.6", "a browsing buyer produces no lead and exposes no contact details")

    # -- 15.7 [MVP] ---------------------------------------------------------------------------
    @gate.criterion("15.7", "income_band appears nowhere in any seller-facing payload")
    def _() -> str:
        # The field names, the exact figure, and **every band value** -- which is stronger
        # than scanning for the bare word "band" and does not risk a false positive on a
        # generated dealer name that happens to contain it. `/seller/dealers` lists 108 of
        # them, so a broad substring here would eventually go red for the wrong reason.
        terms = (
            "income",
            "88000",
            "88,000",
            "employer",
            "contoso",
            "salary",
            *(band.value for band in IncomeBand),
        )
        with memory_backend():
            from src.api.main import app

            with TestClient(app) as buyer, TestClient(app) as seller:
                listing = _listing_with_dealer(buyer)
                _sign_in(buyer, BUYER)
                added = _add_to_cart(buyer, listing)
                buyer.post(
                    "/cart/checkout",
                    json={"session_id": "gate157", "item_id": added["items"][0]["item_id"]},
                )

                # The buyer really does have all of it on file -- otherwise this proves nothing.
                own = buyer.get("/auth/me").json()
                assert own["profile"]["annual_income"]["amount"].startswith("88000")
                assert own["profile"]["income_band"] == IncomeBand.FROM_50K.value

                _sign_in_seller(seller, str(listing.dealer_id), "gate157-seller@example.com")
                lead_id = seller.get("/seller/leads").json()["leads"][0]["id"]
                payloads = {
                    "/seller/leads": seller.get("/seller/leads").text,
                    "/seller/dealers": seller.get("/seller/dealers").text,
                    "/seller/profile": seller.get("/seller/profile").text,
                    "contacted": seller.post(f"/seller/leads/{lead_id}/contacted").text,
                }

        hits = [
            f"{route}: {term!r}"
            for route, text in payloads.items()
            for term in terms
            if term in text.lower()
        ]
        assert not hits, "income-shaped values reached a seller:\n  " + "\n  ".join(hits)
        return (
            f"buyer holds EUR 88,000 / band '{IncomeBand.FROM_50K.value}' / employer on "
            f"file; {len(terms)} terms scanned (field names, the exact figure, and all "
            f"{len(list(IncomeBand))} band values) across {len(payloads)} seller-facing "
            f"payloads ({sorted(payloads)}), 0 hits"
        )

    # -- 15.8 [MVP] (browser) -----------------------------------------------------------------
    browser_criterion("15.8", "every tier renders as an estimate with its reasoning attached")

    # -- 15.9 [MVP] ---------------------------------------------------------------------------
    @gate.criterion(
        "15.9", "no income band can change a lead's score -- undisclosed, disclosed or absent"
    )
    def _() -> str:
        """Stronger than PLAN-02 §P15's "no hidden penalty for `undisclosed`": income is not
        an input at all (D-079), so this asserts the scorer cannot be *given* one, cannot
        mention one, and produces identical results for buyers who differ only in income.
        """
        # 1. There is no parameter to pass it through.
        parameters = set(inspect.signature(score_lead).parameters)
        leaky = {p for p in parameters if any(t in p for t in ("income", "band", "salary"))}
        assert not leaky, f"the scorer accepts income-shaped arguments: {leaky}"

        # 2. Passing one is a TypeError, not a silently ignored kwarg.
        for band in [*IncomeBand, None]:
            try:
                score_lead(  # type: ignore[call-arg]
                    events=(LeadEvent.CART_ADD,),
                    target_date=None,
                    today=date(2026, 8, 9),
                    budget=None,
                    price=None,
                    income_band=band,
                )
            except TypeError:
                continue
            raise AssertionError(f"the scorer accepted income_band={band}")

        # 3. End to end: three buyers identical but for income score identically.
        #
        # Every client is opened *before* any of them writes. Entering `TestClient(app)` runs
        # the app's lifespan, which rebuilds `app.state` -- so a client opened halfway through
        # would silently wipe the lead store and this criterion would fail as "1 lead, not 3"
        # for a reason that has nothing to do with income.
        incomes = (
            ("undisclosed", None),
            ("100k_plus", {"amount": "250000", "currency": "EUR"}),
            ("under_25k", {"amount": "18000", "currency": "EUR"}),
        )
        with memory_backend():
            from src.api.main import app

            scores: dict[str, float] = {}
            with (
                TestClient(app) as seller,
                TestClient(app) as first,
                TestClient(app) as second,
                TestClient(app) as third,
            ):
                listing = _listing_with_dealer(seller)
                for client, (label, income) in zip((first, second, third), incomes, strict=True):
                    _sign_in(
                        client,
                        {
                            **BUYER,
                            "email": f"gate159-{label}@example.com",
                            "profile": {
                                "city": "Berlin",
                                "country": "DE",
                                "annual_income": income,
                            },
                        },
                    )
                    _add_to_cart(client, listing)

                _sign_in_seller(seller, str(listing.dealer_id), "gate159-seller@example.com")
                for lead in seller.get("/seller/leads").json()["leads"]:
                    scores[lead["buyer"]["email"]] = lead["score"]

        assert len(scores) == 3, f"expected 3 leads, got {len(scores)}"
        assert len(set(scores.values())) == 1, f"income changed a score: {scores}"
        return (
            f"the scorer has no income parameter and rejects one for all "
            f"{len(list(IncomeBand))} bands + None; three buyers differing only in income "
            f"(none / EUR 250k / EUR 18k) all scored {next(iter(set(scores.values()))):.6f}"
        )

    # -- 15.10 [MVP] (browser) ----------------------------------------------------------------
    browser_criterion(
        "15.10", "DEMO_MODE drives a buyer action to a live seller dashboard, no keys"
    )

    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Exit gate for PHASE 15 -- SELLER CONSOLE")
    parser.parse_args()
    return build_gate().run()


if __name__ == "__main__":
    raise SystemExit(main())
