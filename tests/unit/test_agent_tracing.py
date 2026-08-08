"""OpenTelemetry tracing (PHASE-9 §3): redaction, span shapes, and the trace `demo.py`
produces -- the same mechanisms gate 9.1-9.3/9.6 assert on, exercised here at the faster
`pytest tests` cadence rather than only when a gate script runs.
"""

from __future__ import annotations

from opentelemetry import trace

from src.adapters.store import InMemoryListingStore
from src.agent.demo import run_demo_session
from src.agent.phase_machine import Phase
from src.agent.tracing import (
    clear_captured_spans,
    configure_tracing,
    get_captured_spans,
    get_tracer,
    phase_span,
    redact_attributes,
    subagent_span,
    tool_call_span,
)


def test_configure_tracing_is_idempotent() -> None:
    first = configure_tracing()
    second = configure_tracing()
    assert first is second


def test_redact_attributes_masks_email_but_keeps_length_shape() -> None:
    raw = "jane.doe@example.com"
    redacted = redact_attributes({"utterance": raw})
    assert redacted["utterance"] == f"email:<redacted:{len(raw)}>"


def test_redact_attributes_masks_phone_numbers() -> None:
    raw = "+31 6 1234 5678"
    redacted = redact_attributes({"note": f"call me at {raw}"})
    value = redacted["note"]
    assert isinstance(value, str)
    assert value.startswith("phone:<redacted:")
    assert "1234" not in value


def test_redact_attributes_masks_by_key_name_even_without_a_regex_match() -> None:
    redacted = redact_attributes({"full_name": "Jane Smith"})
    assert redacted["full_name"] == "pii:<redacted:10>"


def test_redact_attributes_leaves_ordinary_values_untouched() -> None:
    redacted = redact_attributes({"tool.name": "search_cars", "count": 5, "ok": True})
    assert redacted == {"tool.name": "search_cars", "count": 5, "ok": True}


def test_redact_attributes_handles_empty_and_none() -> None:
    assert redact_attributes(None) == {}
    assert redact_attributes({}) == {}


def test_phase_and_tool_call_spans_carry_the_documented_attributes() -> None:
    configure_tracing()
    clear_captured_spans()
    tracer = get_tracer()
    with tracer.start_as_current_span("session"):
        with phase_span(Phase.INTERVIEW) as span:
            span.set_attribute("phase.turns", 1)
            with tool_call_span("interview_turn", {"utterance": "hello"}):
                pass

    spans = get_captured_spans()
    phase = next(s for s in spans if s.name == "phase.interview")
    tool = next(s for s in spans if s.name == "tool.interview_turn")

    assert phase.attributes is not None and phase.attributes["phase.turns"] == 1
    assert tool.attributes is not None
    assert tool.attributes["tool.name"] == "interview_turn"
    assert isinstance(tool.attributes["tool.args_hash"], str)
    assert len(tool.attributes["tool.args_hash"]) == 64
    assert tool.attributes["tool.input.utterance"] == "hello"
    # both spans belong to the same trace as the "session" root they were opened inside
    session_span = next(s for s in spans if s.name == "session")
    assert phase.context.trace_id == session_span.context.trace_id
    assert tool.context.trace_id == session_span.context.trace_id


def test_subagent_spans_nest_under_the_ambient_current_span() -> None:
    configure_tracing()
    clear_captured_spans()
    tracer = get_tracer()
    with tracer.start_as_current_span("phase.research") as research_span:
        with subagent_span("mock_drivenow") as span:
            span.set_attribute("researcher.candidate_count", 3)

    spans = get_captured_spans()
    researcher = next(s for s in spans if s.name == "researcher.mock_drivenow")
    assert researcher.parent is not None
    assert researcher.parent.span_id == research_span.get_span_context().span_id
    assert researcher.attributes is not None
    assert researcher.attributes["researcher.source"] == "mock_drivenow"


async def test_full_demo_session_produces_one_trace_with_all_four_phases() -> None:
    """The same shape gate 9.1 asserts, at unit-test speed."""
    configure_tracing()
    clear_captured_spans()
    store = InMemoryListingStore.seeded()
    result = await run_demo_session(
        ["I want to buy a sedan under 30000 euros by 2026-10-01"],
        store=store,
        session_id="test-tracing-full-session",
    )
    assert result.state.booking_status == "draft_submitted"

    spans = get_captured_spans()
    session_spans = [s for s in spans if s.name == "session"]
    assert len(session_spans) == 1
    trace_id = session_spans[0].context.trace_id

    expected = {"phase.interview", "phase.research", "phase.recommend", "phase.transact"}
    present = {s.name for s in spans if s.name in expected}
    assert present == expected
    assert all(s.context.trace_id == trace_id for s in spans)


async def test_researcher_spans_overlap_and_nest_under_research_phase() -> None:
    """The same shape gate 9.3 asserts, at unit-test speed."""
    configure_tracing()
    clear_captured_spans()
    store = InMemoryListingStore.seeded()
    await run_demo_session(
        ["I want to buy an suv under 30000 euros by 2026-10-01"],
        store=store,
        session_id="test-tracing-researchers",
    )

    spans = get_captured_spans()
    researchers = [s for s in spans if s.name.startswith("researcher.")]
    assert len(researchers) == 2
    research_phase = next(s for s in spans if s.name == "phase.research")
    for r in researchers:
        assert r.parent is not None
        assert r.parent.span_id == research_phase.context.span_id
    a, b = researchers
    assert a.start_time is not None and a.end_time is not None
    assert b.start_time is not None and b.end_time is not None
    assert a.start_time < b.end_time and b.start_time < a.end_time


async def test_pii_bearing_utterance_is_redacted_before_it_reaches_a_captured_span() -> None:
    """Gate 9.6's mechanism: the value that would carry raw PII into a span attribute is
    scrubbed by the export-path redaction hook (CONSTITUTION IV.1), not merely absent.
    """
    configure_tracing()
    clear_captured_spans()
    store = InMemoryListingStore.seeded()
    raw_email = "jane.doe@example.com"
    await run_demo_session(
        [f"I want to buy a sedan under 30000 euros by 2026-10-01, my email is {raw_email}"],
        store=store,
        session_id="test-tracing-pii",
    )

    spans = get_captured_spans()
    interview_span = next(s for s in spans if s.name == "tool.interview_turn")
    assert interview_span.attributes is not None
    value = interview_span.attributes["tool.input.utterance"]
    assert isinstance(value, str)
    assert raw_email not in value
    assert value.startswith("email:<redacted:")


def test_raw_otel_tracer_api_never_needs_this_module_imported_to_be_safe() -> None:
    """`for_audience`'s span wrapper (`src/mcp/audience.py`) calls `trace.get_tracer(...)`
    directly rather than importing `configure_tracing` -- this is what makes that safe in a
    process that never configures tracing at all: the default global provider is a no-op, so
    `start_as_current_span` is always a harmless context manager, never a crash.
    """
    tracer = trace.get_tracer("cardinal.mcp.smoke-test")
    with tracer.start_as_current_span("noop-check"):
        pass
