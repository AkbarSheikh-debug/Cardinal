"""OpenTelemetry tracing (PHASE-9 §3): one trace per session, phase/tool-call/subagent spans
the auto-instrumentor can't know about, and the redaction hook CONSTITUTION IV.1 requires
before anything leaves this process.

`configure_tracing()` always attaches an in-memory exporter (`get_captured_spans` is what
gate 9's own assertions read back) and, only when Langfuse credentials are present in the
environment, also attaches a real OTLP exporter pointed at Langfuse's own ingestion endpoint
-- fire-and-forget, per PHASE-9 §8's risk table ("export failure logs a warning and never
blocks a turn"): `BatchSpanProcessor` already catches and logs whatever its exporter raises,
so no extra try/except is needed around a live export call itself, only around building the
exporter (a bad host/URL should not stop the app from booting).

Both exporters sit behind `RedactingSpanExporter` -- IV.1's "redact before export, not
after": every span is copied with its attributes scrubbed immediately before whichever
exporter's `.export()` actually runs, so an unredacted attribute is never the one that leaves
the process, in memory or over the network.

`src/mcp/audience.py` instruments every registered tool call with its own tracer instead of
importing this module -- `src/mcp` never imports `src/agent` (PLAN-00 §2's one-way layering;
`agent` imports `mcp`'s server builders, never the reverse) -- but both share one globally
configured `TracerProvider`, since OpenTelemetry's API/SDK split is built for exactly this:
any module can call `trace.get_tracer(__name__)` and get real spans once *anyone* has called
`configure_tracing()`, and a harmless no-op tracer otherwise.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.agent.guardrails import hash_args
from src.agent.phase_machine import Phase

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer
    from opentelemetry.util.types import AttributeValue

logger = logging.getLogger(__name__)

SERVICE_NAME = "cardinal"
TRACER_NAME = "cardinal.agent"

#: A span attribute value is a scalar (or a homogeneous sequence of one) per the OTel spec --
#: this is the subset of `tool_input`'s values worth attaching directly, so a debugger can
#: see what a call actually carried without needing the redaction hook to handle nested JSON.
_ATTRIBUTE_SCALAR_TYPES = (str, bool, int, float)

# -- redaction (CONSTITUTION IV.1) ---------------------------------------------------------

#: Key-shaped signal: a field whose *name* says it carries personal data, whatever its value
#: looks like syntactically (a bare "John Smith" has no regex signature an email/phone has).
#: `income`/`salary`/`employer` joined this list with PLAN-02 P12 (§0.3): `annual_income` is
#: the most sensitive field the system collects, and `income_band` -- while coarse -- is
#: still a financial fact about a named person once it sits next to their email in a trace.
#: `employer` is free text the buyer typed, so it can carry anything at all.
_PII_KEY_RE = re.compile(
    r"(email|phone|address|full_?name|card_?number|ssn|passport|income|salary|employer)", re.I
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){7,14}\d(?!\d)")


def _redact_scalar(key: str, value: AttributeValue) -> AttributeValue:
    if not isinstance(value, str):
        # A key-shaped match still redacts a non-string: an income attached as a bare number
        # is exactly as identifying as one attached as text, and returning it untouched
        # because it happened not to be a `str` is the kind of gap that only shows up in a
        # trace nobody reads until it matters.
        return f"pii:<redacted:{type(value).__name__}>" if _PII_KEY_RE.search(key) else value
    if _EMAIL_RE.search(value):
        return f"email:<redacted:{len(value)}>"
    if _PHONE_RE.search(value):
        return f"phone:<redacted:{len(value)}>"
    if _PII_KEY_RE.search(key):
        return f"pii:<redacted:{len(value)}>"
    return value


def redact_attributes(attributes: Mapping[str, AttributeValue] | None) -> dict[str, AttributeValue]:
    """Redact values, keep shapes (IV.1): `email:<redacted:14>`, never a bare deletion --
    a span with a field silently missing is harder to debug than one that visibly says why.
    """
    if not attributes:
        return {}
    return {key: _redact_scalar(key, value) for key, value in attributes.items()}


def _redact_span(span: ReadableSpan) -> ReadableSpan:
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=redact_attributes(span.attributes),
        events=span.events,
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class RedactingSpanExporter(SpanExporter):
    """Wraps another exporter; every span it forwards has already been through
    `_redact_span`. This is the "in the export path, before the network call" IV.1 asks for --
    the wrapped exporter never sees an unredacted attribute, whether that exporter writes to
    memory (gate 9.6 scans this one) or POSTs to Langfuse.
    """

    def __init__(self, wrapped: SpanExporter) -> None:
        self._wrapped = wrapped

    def export(self, spans: Iterable[ReadableSpan]) -> SpanExportResult:
        return self._wrapped.export([_redact_span(span) for span in spans])

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)


# -- provider configuration ------------------------------------------------------------------

_MEMORY_EXPORTER = InMemorySpanExporter()
_configured = False


def _build_langfuse_exporter() -> SpanExporter | None:
    """`None` when no Langfuse credentials are set -- tracing still works locally (gate 9's
    own assertions never need this), and a session without them is not an error
    (PHASE-9 §8: "Langfuse becomes a hard runtime dependency" is the risk this guards against).
    """
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return None
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        return OTLPSpanExporter(
            endpoint=f"{host}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {token}"},
        )
    except Exception:
        logger.warning("Langfuse OTLP exporter could not be built; tracing stays local-only")
        return None


def configure_tracing(*, force: bool = False) -> TracerProvider:
    """Idempotent: the first caller (API startup, `DEMO_MODE`, or a gate script) wins, and
    every later call just returns the same provider -- OpenTelemetry's global provider can
    only meaningfully be set once per process anyway.
    """
    global _configured
    provider = trace.get_tracer_provider()
    if _configured and not force and isinstance(provider, TracerProvider):
        return provider

    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(_MEMORY_EXPORTER)))

    langfuse_exporter = _build_langfuse_exporter()
    if langfuse_exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(RedactingSpanExporter(langfuse_exporter)))

    trace.set_tracer_provider(provider)
    _configured = True
    return provider


def get_tracer() -> Tracer:
    return trace.get_tracer(TRACER_NAME)


def get_captured_spans() -> tuple[ReadableSpan, ...]:
    """Every span this process has finished and exported to the in-memory exporter, already
    redacted (`configure_tracing` wraps it in `RedactingSpanExporter`) -- what gate 9.1-9.3 and
    9.6 inspect as "a real export" rather than reading our own bookkeeping back to itself.
    """
    return tuple(_MEMORY_EXPORTER.get_finished_spans())


def clear_captured_spans() -> None:
    _MEMORY_EXPORTER.clear()


# -- named spans (PHASE-9 §3's table) --------------------------------------------------------


@contextmanager
def phase_span(phase: Phase, *, context: Context | None = None) -> Iterator[Span]:
    """One span per phase *stay* -- a session that visits RESEARCH twice (gate 3.5's backward
    transition) gets two `phase.research` spans, which is the honest shape: the agent really
    was in that phase twice, not once for twice as long.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(f"phase.{phase.value}", context=context) as span:
        yield span


@contextmanager
def tool_call_span(tool_name: str, tool_input: Mapping[str, Any]) -> Iterator[Span]:
    """Gate 9.2: args hash + duration (the span's own start/end time) for every tool call the
    demo path makes. `tool.input.<key>` attaches each scalar argument directly, unredacted at
    this point -- deliberately, so the redaction hook (gate 9.6) has something real to prove
    itself against rather than a span that was already safe by construction.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(f"tool.{tool_name}") as span:
        span.set_attribute("tool.name", tool_name)
        span.set_attribute("tool.args_hash", hash_args(dict(tool_input)))
        for key, value in tool_input.items():
            if isinstance(value, _ATTRIBUTE_SCALAR_TYPES):
                span.set_attribute(f"tool.input.{key}", value)
        yield span


@contextmanager
def subagent_span(source: str, *, kind: str = "researcher") -> Iterator[Span]:
    """Gate 9.3: one span per marketplace source, opened while its parent (`phase.research`)
    is the ambient current span -- `asyncio.gather`'s tasks snapshot that context at creation,
    which is what makes the resulting spans genuine, overlapping siblings rather than a
    sequential chain that merely looks concurrent in the final candidate list.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(f"{kind}.{source}") as span:
        span.set_attribute(f"{kind}.source", source)
        yield span


@contextmanager
def scoring_span(*, candidate_count: int, seed: str) -> Iterator[Span]:
    """`scoring.rank` (PHASE-9 §3): candidate count and seed set up front; the caller (who
    alone knows the weights `rank()` chose and the resulting order) fills in
    `scoring.weight.<criterion>` / `scoring.determinism_hash` on the yielded span afterward.
    `src/domain/ranking.py` stays pure and never imports this (CONSTITUTION II.1) -- the
    caller wraps its own call to `rank()`, this module never calls into domain itself.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("scoring.rank") as span:
        span.set_attribute("scoring.candidate_count", candidate_count)
        span.set_attribute("scoring.seed", seed)
        yield span
