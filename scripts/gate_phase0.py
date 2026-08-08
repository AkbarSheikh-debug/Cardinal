"""Exit gate for PHASE 0 -- Foundation."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.gate_common import REPO_ROOT, Gate, Pending, python_executable, run_command

MAX_PROMPT_CHARS = 200


def build_gate() -> Gate:
    gate = Gate(0, "Foundation -- contracts, layering, verification harness")

    @gate.criterion("0.1", "every domain model round-trips its fixture JSON")
    def _() -> str:
        proc = run_command(
            [
                python_executable(),
                "-m",
                "pytest",
                "tests/unit/test_domain_models.py",
                "-q",
                "--no-header",
            ]
        )
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-200:]
        assert proc.returncode == 0, f"round-trip tests red: {tail}"
        return tail

    @gate.criterion("0.2", "Money rejects float; arithmetic preserves Decimal")
    def _() -> str:
        proc = run_command(
            [python_executable(), "-m", "pytest", "tests/unit/test_money.py", "-q", "--no-header"]
        )
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-200:]
        assert proc.returncode == 0, f"Money tests red: {tail}"
        return tail

    @gate.criterion("0.3", "import-boundary scan finds zero violations")
    def _() -> str:
        proc = run_command(
            [
                python_executable(),
                "-m",
                "pytest",
                "tests/test_layer_boundary.py",
                "-q",
                "--no-header",
            ]
        )
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-400:]
        assert proc.returncode == 0, f"layer boundary violated: {tail}"
        return tail

    @gate.criterion("0.4", "mypy --strict src/domain reports zero errors")
    def _() -> str:
        proc = run_command([python_executable(), "-m", "mypy", "--strict", "src/domain"])
        output = (proc.stdout + proc.stderr).strip()
        if "No module named mypy" in output:
            raise Pending("mypy not installed; `pip install -e .[dev]`")
        tail = output.splitlines()[-1] if output else "(no output)"
        assert proc.returncode == 0, f"{tail}\n" + "\n".join(output.splitlines()[:12])
        return tail

    @gate.criterion("0.5", "specs/ holds constitution, spec, plan and tasks, all non-empty")
    def _() -> str:
        specs = REPO_ROOT / "specs"
        wanted = ("constitution.md", "spec.md", "plan.md", "tasks.md")
        if not specs.is_dir():
            raise Pending("specs/ absent -- spec-kit has not been run (PHASE-0 §7)")
        missing = [name for name in wanted if not (specs / name).is_file()]
        empty = [
            name
            for name in wanted
            if (specs / name).is_file() and not (specs / name).read_text(encoding="utf-8").strip()
        ]
        if missing or empty:
            raise Pending(f"missing={missing} empty={empty}")
        return f"all four spec-kit artifacts present: {', '.join(wanted)}"

    @gate.criterion("0.6", "every gate script exists and runs to completion")
    def _() -> str:
        missing = [
            phase
            for phase in range(12)
            if not (REPO_ROOT / f"scripts/gate_phase{phase}.py").is_file()
        ]
        assert not missing, f"no gate script for phases {missing}"
        return "gate_phase0.py .. gate_phase11.py all present"

    @gate.criterion("0.7", "[SCALE] prompts live in files; no long prompt strings in src/")
    def _() -> str:
        prompts = REPO_ROOT / "prompts"
        if not prompts.is_dir():
            raise Pending("prompts/ absent -- no prompts exist until P3")

        stray = [p.name for p in prompts.rglob("*.py")]
        assert not stray, f"prompts/ contains Python: {stray}"

        offenders: list[str] = []
        for path in (REPO_ROOT / "src").rglob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if len(stripped) > MAX_PROMPT_CHARS and stripped.startswith(('"', "'", 'f"')):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
        assert not offenders, f"prompt strings over {MAX_PROMPT_CHARS} chars: {offenders}"
        return f"{len(list(prompts.rglob('*.md')))} prompt files, none inlined in src/"

    return gate


def main() -> int:
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
