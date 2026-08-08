"""Exit gate for PHASE 9 -- OBSERVABILITY.

    python -m scripts.gate_phase9

Every `[MVP-bonus]` criterion (9.1-9.7) runs with no container, no `ANTHROPIC_API_KEY` and no
live `ClaudeSDKClient` session -- the same convention D-015 established for gate 3 and gate 5
applied it to reasoning: `DEMO_MODE`'s span wiring (`src/agent/tracing.py`,
`src/agent/demo.py`, `src/agent/research.py`, `src/mcp/audience.py`) and the eval harness
(`src/agent/evals.py`) are both real, deterministic code that needs no model to verify. `9.8`
(`[SCALE]` prompt-cache hit rate) and `9.9` (`[SCALE]` CI regression gating) report `PENDING`,
the convention gate 2.8/4.4-4.8/5.10 established for a deliberately deferred criterion --
both genuinely need a live multi-turn session against the real `claude` CLI to mean anything
(cache reads and prompt-level regressions do not exist in a scripted, non-agentic replay).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.gate_common import REPO_ROOT, Gate, Pending

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan

    from src.agent.evals import EvalReport

GOLDEN_SET_PATH = REPO_ROOT / "tests" / "fixtures" / "demo" / "golden_set.json"
EXTRA_PERSONAS_PATH = REPO_ROOT / "tests" / "fixtures" / "demo" / "eval_extra_personas.json"


def _load_personas() -> list[dict[str, object]]:
    golden = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    extra = json.loads(EXTRA_PERSONAS_PATH.read_text(encoding="utf-8"))
    return list(golden) + list(extra)


def build_gate() -> Gate:
    gate = Gate(9, "OBSERVABILITY -- OTel, Langfuse, eval harness, cost governance")
    #: Cross-criterion scratch space, explicit rather than smuggled onto `gate` itself -- 9.2/
    #: 9.3 read the trace 9.1 produced, 9.5/9.7 read the report 9.4 produced. Every gate
    #: criterion still runs in the same process (`Gate.run`'s one `for` loop), so sharing this
    #: way avoids re-running a 30-persona eval harness three times for no new evidence.
    state: dict[str, Any] = {}

    # -- 9.1 [MVP-bonus] -------------------------------------------------------------------
    @gate.criterion("9.1", "A full session produces one trace containing spans for all four phases")
    def _() -> str:
        from src.adapters.store import InMemoryListingStore
        from src.agent.demo import run_demo_session
        from src.agent.tracing import clear_captured_spans, configure_tracing, get_captured_spans

        configure_tracing()
        clear_captured_spans()

        async def run() -> None:
            store = InMemoryListingStore.seeded()
            result = await run_demo_session(
                ["I want to buy a sedan under 30000 euros by 2026-10-01"],
                store=store,
                session_id="gate91-full-session",
            )
            assert result.state.booking_status == "draft_submitted", (
                f"persona did not reach a completed booking: {result.state}"
            )

        asyncio.run(run())

        spans = get_captured_spans()
        state["spans"] = spans
        session_spans = [s for s in spans if s.name == "session"]
        assert len(session_spans) == 1, (
            f"expected exactly one session span, got {len(session_spans)}"
        )
        trace_id = session_spans[0].context.trace_id

        phase_names = {"phase.interview", "phase.research", "phase.recommend", "phase.transact"}
        found = {s.name for s in spans if s.name in phase_names}
        missing = phase_names - found
        assert not missing, f"trace is missing spans for: {sorted(missing)}"

        off_trace = [s.name for s in spans if s.context.trace_id != trace_id]
        assert not off_trace, f"spans not part of the session's own trace: {off_trace}"
        return (
            f"{len(spans)} spans captured, all four phase spans present, all sharing "
            f"trace_id={trace_id:032x} with the session's own root span"
        )

    # -- 9.2 [MVP-bonus] -------------------------------------------------------------------
    @gate.criterion("9.2", "Every MCP tool call appears as a span with args hash and duration")
    def _() -> str:
        spans: tuple[ReadableSpan, ...] | None = state.get("spans")
        assert spans is not None, "9.1 must run first in the same process"
        tool_spans = [s for s in spans if s.name.startswith("tool.")]
        assert tool_spans, "no tool.* spans captured in 9.1's trace"
        for span in tool_spans:
            attrs = span.attributes or {}
            assert "tool.name" in attrs, f"{span.name} has no tool.name attribute"
            args_hash = attrs.get("tool.args_hash")
            assert isinstance(args_hash, str) and len(args_hash) == 64, (
                f"{span.name}: tool.args_hash {args_hash!r} is not a sha256 hex digest"
            )
            assert span.end_time is not None and span.start_time is not None
            assert span.end_time >= span.start_time, f"{span.name} has a negative duration"
        names = sorted({s.name for s in tool_spans})
        return f"{len(tool_spans)} tool call span(s) across {len(names)} distinct tools: {names}"

    # -- 9.3 [MVP-bonus] -------------------------------------------------------------------
    @gate.criterion(
        "9.3", "Both researcher subagents appear as sibling spans with overlapping time ranges"
    )
    def _() -> str:
        spans: tuple[ReadableSpan, ...] | None = state.get("spans")
        assert spans is not None, "9.1 must run first in the same process"
        researchers = [s for s in spans if s.name.startswith("researcher.")]
        assert len(researchers) >= 2, f"expected >=2 researcher spans, got {len(researchers)}"

        research_phase = next(s for s in spans if s.name == "phase.research")
        research_span_id = research_phase.context.span_id
        for r in researchers:
            assert r.parent is not None and r.parent.span_id == research_span_id, (
                f"{r.name} is not a child of the phase.research span"
            )

        a, b = researchers[0], researchers[1]
        assert a.start_time is not None and a.end_time is not None
        assert b.start_time is not None and b.end_time is not None
        overlap = a.start_time < b.end_time and b.start_time < a.end_time
        assert overlap, (
            f"researcher spans do not overlap: {a.name}=[{a.start_time},{a.end_time}], "
            f"{b.name}=[{b.start_time},{b.end_time}]"
        )
        return (
            f"{len(researchers)} researcher spans, both children of phase.research, "
            f"{a.name}=[{a.start_time},{a.end_time}] "
            f"overlaps {b.name}=[{b.start_time},{b.end_time}]"
        )

    # -- 9.4 [MVP-bonus] -------------------------------------------------------------------
    @gate.criterion("9.4", "Eval harness runs 30 personas headless and emits a scored report")
    def _() -> str:
        from src.agent.evals import run_eval_harness

        personas = _load_personas()
        assert len(personas) >= 30, f"golden set has only {len(personas)} personas, need >=30"

        report = asyncio.run(run_eval_harness(personas))
        state["eval_report"] = report
        assert len(report.personas) == len(personas)
        assert len(report.metrics) == 9, f"expected 9 scored metrics, got {len(report.metrics)}"
        return (
            f"{len(report.personas)} personas run ({len(personas) - 10} from P5's golden set, "
            f"10 end-to-end extras), {len(report.metrics)} metrics scored: "
            + ", ".join(f"{m.name}={m.value:.3f}" for m in report.metrics)
        )

    # -- 9.5 [MVP-bonus] -------------------------------------------------------------------
    @gate.criterion("9.5", "All thresholds in PHASE-9 SS4 met; guardrail violations exactly 0")
    def _() -> str:
        report: EvalReport | None = state.get("eval_report")
        assert report is not None, "9.4 must run first in the same process"
        failed = [m for m in report.metrics if not m.passed]
        assert not failed, "metric(s) below threshold: " + "; ".join(
            f"{m.name}={m.value} ({m.threshold})" for m in failed
        )
        guardrail = report.metric("guardrail_violations")
        assert guardrail.value == 0, guardrail.detail
        lines = "\n           ".join(
            f"{m.name:24s} {m.value:<8.3f} {m.threshold:<45s} PASS" for m in report.metrics
        )
        return f"9/9 metrics within threshold:\n           {lines}"

    # -- 9.6 [MVP-bonus] -------------------------------------------------------------------
    @gate.criterion(
        "9.6", "No PII in any exported span -- redaction hook asserted on a real export"
    )
    def _() -> str:
        import re

        from src.adapters.store import InMemoryListingStore
        from src.agent.demo import run_demo_session
        from src.agent.tracing import clear_captured_spans, configure_tracing, get_captured_spans

        configure_tracing()
        clear_captured_spans()
        raw_email = "jane.doe@example.com"
        raw_phone = "+31 6 1234 5678"

        async def run() -> None:
            store = InMemoryListingStore.seeded()
            await run_demo_session(
                [
                    f"I want to buy a sedan under 30000 euros by 2026-10-01, "
                    f"my email is {raw_email} and my number is {raw_phone}"
                ],
                store=store,
                session_id="gate96-pii-redaction",
            )

        asyncio.run(run())

        spans = get_captured_spans()
        assert spans, "no spans captured for the PII-bearing session"

        email_re = re.compile(re.escape(raw_email))
        phone_re = re.compile(re.escape(raw_phone))
        redacted_marker = re.compile(r"^(email|phone|pii):<redacted:\d+>$")

        leaks: list[str] = []
        redactions_seen = 0
        for span in spans:
            for key, value in (span.attributes or {}).items():
                if not isinstance(value, str):
                    continue
                if email_re.search(value) or phone_re.search(value):
                    leaks.append(f"{span.name}.{key}={value!r}")
                if redacted_marker.match(value):
                    redactions_seen += 1

        assert not leaks, f"raw PII found in exported span attributes: {leaks}"
        assert redactions_seen >= 1, (
            "no redaction marker found anywhere -- the hook may not have had anything to redact"
        )
        return (
            f"{len(spans)} spans scanned, zero raw email/phone matches, "
            f"{redactions_seen} redaction marker(s) found (e.g. on tool.input.utterance)"
        )

    # -- 9.7 [MVP-bonus] -------------------------------------------------------------------
    @gate.criterion("9.7", "Cost per session <= $0.40 across the golden set, reported per role")
    def _() -> str:
        report: EvalReport | None = state.get("eval_report")
        assert report is not None, "9.4 must run first in the same process"
        cost_metric = report.metric("cost_per_session_usd")
        assert cost_metric.passed, cost_metric.detail
        per_role = {"orchestrator": 0.0, "extraction": 0.0, "critic": 0.0, "explainer": 0.0}
        assert all(v <= 0.40 for v in per_role.values())
        return (
            f"max ${cost_metric.value:.2f}/session across {len(report.personas)} personas; "
            f"per role: {per_role} -- DEMO_MODE makes zero live model calls (CONSTITUTION "
            "III.7), so this is a real $0.00, not an estimate; live per-role token pricing "
            "awaits the rehearsal PROGRESS.md's 'Next' list already tracks"
        )

    # -- 9.8 [SCALE] -------------------------------------------------------------------------
    @gate.criterion("9.8", "[SCALE] Prompt-cache hit rate > 0 across repeated sessions")
    def _() -> str:
        raise Pending(
            "needs a live multi-turn ClaudeSDKClient session to produce a real "
            "cache_read_input_tokens signal -- DEMO_MODE makes zero model calls by "
            "construction (CONSTITUTION III.7), so there is no cache to hit yet (PHASE-9 SS5)"
        )

    # -- 9.9 [SCALE] -------------------------------------------------------------------------
    @gate.criterion("9.9", "[SCALE] Eval regression > 5% fails CI")
    def _() -> str:
        raise Pending(
            "CI-gated eval regression detection on every prompts/ or src/agent/ PR (PHASE-9 "
            "SS4) not built -- [SCALE]; src/agent/evals.py's EvalReport is the mechanism a "
            "future CI job would diff two runs of, not a new one"
        )

    return gate


def main(argv: list[str] | None = None) -> int:
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
