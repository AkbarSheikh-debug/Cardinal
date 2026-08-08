# PHASE 9 — Observability & Evals

**Owns:** knowing whether the agent is any good, and what it costs. Tracing, evaluation, and budget
governance.

The brief lists this as a bonus. For a hackathon it's a differentiator; for a startup it's the
difference between shipping improvements and guessing. It is also the only phase that tells you
whether a prompt change made things *worse*.

---

## 1. Objective

Every session fully traced, every release evaluated against a golden set in CI, every session's cost
bounded and attributed.

## 2. Scope

### In
- `[MVP-bonus]` OpenTelemetry instrumentation → Langfuse
- `[MVP-bonus]` Spans per phase, per tool call, per subagent
- `[MVP-bonus]` Eval harness over golden personas
- `[SCALE]` CI-gated evals with regression detection
- `[SCALE]` Per-session cost budget + hard cap
- `[SCALE]` Reasoning-replay timeline surfaced in-product
- `[SCALE]` Online evals on real sessions, sampled

### Out
- PII redaction *policy* — P10 owns it. P9 owns the redaction *hook* in the export path.

---

## 3. Tracing

```bash
pip install langfuse claude-agent-sdk openinference-instrumentation-claude-agent-sdk
```

```python
from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
ClaudeAgentSDKInstrumentor().instrument()
```

One line auto-generates GenAI-semantic-convention spans for every model request and tool execution.
On top of it, add spans the instrumentor can't know about:

| Span | Attributes |
|---|---|
| `phase.interview` / `.research` / `.recommend` / `.transact` | turns, exit predicate, duration |
| `scoring.rank` | candidate count, weights, seed, determinism hash |
| `tco.compute` | horizon, break-even month |
| `a2ui.render` | surface id, component count, compiled-vs-`compose_surface` |
| `mcp_app.rpc` | method, resource uri, allowed/blocked |
| `memory.recall` | tier, hits, tokens returned |

**The trace and the `ReasoningTrace` surface are the same data.** What the judge sees on screen is
what lands in Langfuse — that's a much stronger claim than two separate systems that happen to
agree, and it costs nothing if you emit both from one event stream.

---

## 4. The eval harness

Golden set: **30 personas**, each with a scripted conversation and an expected outcome. Twenty come
from P5's ranking golden set; ten exercise paths that only appear end-to-end (backward transition,
zero results, decline at checkout).

| Metric | Definition | Threshold |
|---|---|---|
| **Profile completeness** | Required slots filled above confidence within the turn budget | ≥ 0.95 |
| **Precision@3** | Expected listings appearing in the top 3 | ≥ 0.80 |
| **Groundedness** | Rationale claims with a valid `FieldRef` (P5 §6) | 1.00 |
| **Constraint compliance** | Results violating a stated hard filter | 0 |
| **Guardrail violations** | Agent-initiated `confirm_booking`, injection success, PII leak | **0** |
| **Escape-hatch ratio** | `compose_surface` renders / total renders | ≤ 0.15 |
| **Tool-call rate** | Searches per session — catches *under*-calling | 2–8 |
| **Cost/session** | USD, all models | ≤ $0.40 |
| **Latency p50 / p95** | First token to final render | ≤ 8s / ≤ 25s |

Two of these are less obvious and worth keeping. **Tool-call rate** catches the failure where a
model answers from prior knowledge instead of searching — output looks fine, behaviour is wrong.
**Escape-hatch ratio** catches P6's compiler quietly losing to `compose_surface`, which trades
reliability for nothing.

`[SCALE]` — evals run in CI on every PR touching `prompts/` or `src/agent/`. A metric regressing
more than 5% fails the build. That's what makes prompt changes safe to make.

---

## 5. Cost governance `[SCALE]`

Per-session token accounting, attributed by role (orchestrator / extraction / each subagent), with a
hard cap. On approaching the cap: compact, drop to a cheaper model for extraction, and warn — in
that order. On exceeding it: end the turn gracefully with a message, never silently truncate.

Levers, in the order to reach for them:

1. **Result-size caps** (P2 §6) — the largest single lever; a 47-listing dump is 18k tokens
2. **Cheap model for extraction** (P3 §5) — it's the highest-frequency call
3. **Prompt caching** on the stable system prefix — Opus 5's minimum cacheable prefix is 512 tokens,
   so most of our prompts qualify
4. **Effort tuning per role** — `low` for researchers, `xhigh` only for the ranking turn
5. **Compaction** for long sessions

Track cache hit rate explicitly. If `cache_read_input_tokens` is zero across repeated sessions,
something volatile is at the front of the prefix — a timestamp, a session id — and every session is
paying full price. That's a silent 3× cost bug and only the metric reveals it.

---

## 6. Reasoning replay `[SCALE]`

The in-product surface for all of the above: scrub back through a session's decisions, see the
weights at each ranking, the candidates considered, what the critic rejected.

Cheap because the data already exists — it's P4's decision journal joined to the trace. Valuable
because it makes the bonus visible to a user, not just to us, and because "why did it recommend
that?" is the question a dealer's compliance team will ask.

---

## 7. Exit gate

`scripts/gate_phase9.py`:

| # | Criterion |
|---|---|
| 9.1 | A full session produces one trace containing spans for all four phases |
| 9.2 | Every MCP tool call appears as a span with args hash and duration |
| 9.3 | Both researcher subagents appear as sibling spans with overlapping time ranges |
| 9.4 | Eval harness runs 30 personas headless and emits a scored report |
| 9.5 | All thresholds in §4 met; **guardrail violations exactly 0** |
| 9.6 | No PII in any exported span — redaction hook asserted by scanning a real export |
| 9.7 | Cost per session ≤ $0.40 across the golden set, reported per role |
| 9.8 | Prompt-cache hit rate > 0 across repeated sessions (`[SCALE]`) |
| 9.9 | Eval regression > 5% fails CI (`[SCALE]`) |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Evals encode our assumptions, not user value | Two people build expected shortlists independently; disagreements mark criteria that are actually wrong |
| Traces leak PII to a third party | Redaction hook in the export path, before the network call. Gate 9.6 scans real exports, not the code. |
| Langfuse becomes a hard runtime dependency | Instrumentation is fire-and-forget; export failure logs a warning and never blocks a turn |
| Golden set rots as the catalogue changes | Seed is fixed (P1 §4); the golden set pins listing IDs, and a seed change is a deliberate, reviewed event |
| Eval cost on every PR | Sample 10 of 30 on PRs, full 30 on main |
