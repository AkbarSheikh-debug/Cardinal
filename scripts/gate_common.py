"""Shared shape for every `gate_phaseN.py` (PHASE-0 §6).

Each gate prints one line per criterion with `PASS`, `FAIL` or `PENDING`, exits non-zero on
any `FAIL`, and exits 0 when everything unimplemented is `PENDING`. A phase that has not
started reports all-`PENDING` and passes -- that is correct, not broken. It means
`make verify` is green from day one and only turns red on a *regression*.

Criteria **print their evidence**. "1.3 PASS" tells you nothing you can check; "1.3 PASS --
suv: 12 brands" is a number a human can disbelieve.
"""

from __future__ import annotations

import re
import subprocess
import sys
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Gate output contains section signs and brand names like Škoda. Windows consoles default
# to cp1252 and would render those as mojibake in the very output that gets pasted into
# PROGRESS.md as evidence.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


#: Raise this from a criterion that cannot run in this environment -- an unstarted phase, or
#: a check that needs a container nobody started. Distinct from failure on purpose.
class Pending(Exception):
    pass


@dataclass
class Result:
    ident: str
    title: str
    status: Status
    detail: str = ""
    lines: list[str] = field(default_factory=list)


class Gate:
    """Collects criteria, runs them, prints a report, and decides the exit code."""

    def __init__(self, phase: int, title: str) -> None:
        self.phase = phase
        self.title = title
        self._criteria: list[tuple[str, str, Callable[[], str | None]]] = []
        self.results: list[Result] = []

    def criterion(self, ident: str, title: str) -> Callable[[Callable[[], str | None]], None]:
        def register(fn: Callable[[], str | None]) -> None:
            self._criteria.append((ident, title, fn))

        return register

    def run(self) -> int:
        width = 78
        print("=" * width)
        print(f"GATE {self.phase} -- {self.title}")
        print("=" * width)

        for ident, title, fn in self._criteria:
            detail = ""
            extra: list[str] = []
            try:
                returned = fn()
                status = Status.PASS
                detail = returned or ""
            except Pending as exc:
                status, detail = Status.PENDING, str(exc)
            except AssertionError as exc:
                status, detail = Status.FAIL, str(exc) or "assertion failed"
            except Exception as exc:
                status = Status.FAIL
                detail = f"{type(exc).__name__}: {exc}"
                extra = traceback.format_exc().strip().splitlines()[-4:]

            head, *rest = (detail or "").split("\n")
            print(f"  {ident:<6} {status.value:<8} {title}")
            if head:
                print(f"           {head}")
            for line in rest + extra:
                print(f"           {line}")
            self.results.append(Result(ident, title, status, detail, extra))

        return self._summarise(width)

    def _summarise(self, width: int) -> int:
        counts = {status: 0 for status in Status}
        for result in self.results:
            counts[result.status] += 1
        print("-" * width)
        print(
            f"  {counts[Status.PASS]} passed, "
            f"{counts[Status.FAIL]} failed, {counts[Status.PENDING]} pending"
        )
        failed = [r.ident for r in self.results if r.status is Status.FAIL]
        if failed:
            print(f"  GATE {self.phase} RED -- {', '.join(failed)}")
            print("=" * width)
            return 1
        if counts[Status.PENDING]:
            print(f"  GATE {self.phase} GREEN (with {counts[Status.PENDING]} pending)")
        else:
            print(f"  GATE {self.phase} GREEN")
        print("=" * width)
        return 0


def pending_gate(phase: int, title: str, note: str) -> int:
    """A whole phase that has not started yet."""
    gate = Gate(phase, title)

    @gate.criterion(f"{phase}.0", "Phase not started")
    def _() -> str:
        raise Pending(note)

    return gate.run()


def run_command(
    args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def python_executable() -> str:
    return sys.executable


# ---------------------------------------------------------------------------------------------
# Denylist scanning (CONSTITUTION I.1, I.3): shared by gate 8.7 and gate 10.3 so the two check
# the *same* payment-provider list rather than two independently-authored ones that could
# silently drift apart -- CONSTITUTION.md's own "Enforced by" line names both gates for I.1.
# ---------------------------------------------------------------------------------------------

#: `plans/PHASE-8-COMMERCE.md` names "Stripe" once, deliberately, to explain the test-card
#: convention (CONSTITUTION.md does the same for BMW Group in I.3) -- this list covers only
#: what ships, not the plan docs that talk about what ships.
PAYMENT_PROVIDER_TERMS: tuple[str, ...] = (
    "stripe",
    "braintree",
    "adyen",
    "paypal",
    "square",
    "worldpay",
    "checkout.com",
    "authorize.net",
    "klarna",
    "razorpay",
)

DENYLIST_SCAN_DIRS: tuple[str, ...] = ("src", "tests", "scripts")
DENYLIST_EXTRA_FILES: tuple[str, ...] = (
    "pyproject.toml",
    "web/package.json",
    "web/package-lock.json",
)

#: Every file that spells out a denylist literally, across both gates -- excluded from every
#: scan for the same reason a linter's rule config isn't flagged by its own rule. Named here
#: once rather than as a `this_file` computed per-caller, so gate 8.7 and gate 10.3 exclude
#: each other's source too and neither can be made to self-flag by the other's prose.
DENYLIST_AUTHORING_FILES: tuple[Path, ...] = (
    REPO_ROOT / "scripts" / "gate_common.py",
    REPO_ROOT / "scripts" / "gate_phase8.py",
    REPO_ROOT / "scripts" / "gate_phase10.py",
)


def scan_for_terms(
    terms: Sequence[str],
    *,
    scan_dirs: Sequence[str],
    extra_files: Sequence[str],
    exclude_files: Sequence[Path] = (),
) -> tuple[int, list[str]]:
    """Case-insensitive substring scan for `terms` across `scan_dirs` (recursive, relative to
    `REPO_ROOT`) plus `extra_files`. Returns `(files_scanned, hits)` -- `hits` is empty on a
    clean scan, each entry `"path: 'matched text'"`.
    """
    pattern = re.compile("|".join(re.escape(term) for term in terms), re.IGNORECASE)
    exclude = {p.resolve() for p in exclude_files}

    paths: list[Path] = []
    for dirname in scan_dirs:
        paths.extend((REPO_ROOT / dirname).rglob("*"))
    paths.extend(REPO_ROOT / name for name in extra_files)

    scanned = 0
    hits: list[str] = []
    for path in paths:
        if not path.is_file() or path.suffix in {".pyc"} or "__pycache__" in path.parts:
            continue
        if path.resolve() in exclude:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for match in pattern.finditer(text):
            hits.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)!r}")
    return scanned, hits
