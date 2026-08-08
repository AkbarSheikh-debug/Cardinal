# PHASE 3 — Agent

**Owns:** orchestration. The phase machine, the subagent roster, model routing, guardrail hooks,
session durability, and demo mode.

This is where "multistep agent" stops being a claim and becomes a structure you can point at.

---

## 1. Objective

A Claude Agent SDK orchestrator that drives INTERVIEW → RESEARCH → RECOMMEND → TRANSACT with
durable state, parallel research subagents, and a fully canned offline path.

## 2. Scope

### In
- `[MVP]` Phase machine with turn budgets and explicit transitions
- `[MVP]` `ClaudeSDKClient` wiring: `mcp_servers`, `agents`, `hooks`, `can_use_tool`, `session_store`
- `[MVP]` Subagent roster (§4)
- `[MVP]` Model routing: orchestrator vs extraction
- `[MVP]` `DEMO_MODE` — full flow, zero API keys
- `[MVP]` Prompt files under `prompts/`, versioned
- `[SCALE]` Interrupt / steering mid-turn
- `[SCALE]` Compaction strategy for very long sessions
- `[SCALE]` Multi-provider fallback when the primary API rate-limits

### Out
- Memory tiers beyond working state — P4.
- Scoring — P5. The agent *asks for* a ranking; it doesn't compute one.

---

## 3. The phase machine

```
INTERVIEW ──(profile complete)──▶ RESEARCH ──(candidates ranked)──▶ RECOMMEND ──(user picks)──▶ TRANSACT
    ▲                                                                    │
    └────────────────(new constraint invalidates results)────────────────┘
```

Four phases, each with a turn budget and an explicit exit predicate. Ported in shape from the
interview engine in the user's existing Interview Agent repo (`routers/interview.py`) — that
codebase's `PHASE_TURN_LIMITS` / `_advance_phase` structure maps directly and is the largest single
code saving available.

| Phase | Budget | Exit predicate |
|---|---|---|
| INTERVIEW | 12 turns | All required slots above confidence threshold, or budget exhausted (then ask one consolidating question and proceed with what you have) |
| RESEARCH | 6 turns | ≥1 candidate survives hard filters, or infeasibility detected → counterfactual branch (P5) |
| RECOMMEND | 10 turns | User selects a listing, or explicitly disengages |
| TRANSACT | 8 turns | Booking reaches a terminal state |

**Phase state is code-owned.** The model doesn't decide it's "done interviewing" — the predicate
does, evaluated against the typed `RequirementProfile`. That's what makes the A2UI progress surface
derivable and stops the model declaring victory with two empty slots.

**Backward transitions are real.** "Actually, make it under €20k" mid-RECOMMEND invalidates the
ranking and returns to RESEARCH. Handle it explicitly or the demo breaks the first time a judge
changes their mind.

---

## 4. Subagent roster

```python
options = ClaudeAgentOptions(
    model="claude-opus-5",
    effort="high",
    thinking={"type": "adaptive"},          # not budget_tokens — 400s on Opus 5
    mcp_servers={"market": market_sdk, "ui": ui_sdk, "booking": booking_http},
    agents={
        "interviewer": AgentDefinition(...),
        "researcher":  AgentDefinition(...),
        "critic":      AgentDefinition(...),
        "explainer":   AgentDefinition(...),
    },
    hooks={"PreToolUse": [guardrail_matcher]},
    can_use_tool=permission_callback,
    session_store=PostgresSessionStore(),
)
```

| Subagent | Model | Tools | Job |
|---|---|---|---|
| `interviewer` | opus-5, `medium` | none (conversation only) | Elicit requirements. Explicitly told *not* to search — the most common failure is jumping to results with two slots filled. |
| `researcher` ×2 | opus-5, `low` | `search_cars`, `get_listing`, `check_availability` | One per marketplace, **launched in the same turn so they run concurrently**. Returns candidate IDs + a one-line note each, never full records. |
| `critic` | opus-5, `high` | `get_listing` | Reviews the top 5 against every hard filter and the stated budget before anything is shown. Catches the "recommended a car available in November for a September date" class of error. |
| `explainer` | opus-5, `medium` | `get_listing` | Turns a `ScoreBreakdown` into prose with a `FieldRef` behind every claim (P5 §6). |

Keep subagent prompts short and single-purpose — the reference shape is Claude Code's own Explore
agent at ~870 tokens. Long subagent prompts dilute; the useful content is *what not to do*.

**The parallel fan-out is the demonstrable "orchestration" the brief asks for.** Launch both
researchers in one message with two tool calls so they're genuinely concurrent, and make sure the
`ReasoningTrace` surface shows them interleaving — a sequential fallback looks identical in output
and completely different in the trace.

---

## 5. Model routing

| Role | Model | Effort | Rationale |
|---|---|---|---|
| Orchestrator, critic, explainer | `claude-opus-5` | `high`; `xhigh` for the ranking turn | Long-horizon multistep work |
| Slot extraction (runs **every** user turn) | `claude-haiku-4-5` | — | Narrow structured-output task, 5× cheaper, and it's the highest-frequency call in the system |

Slot extraction is a separate, tiny call with `output_config.format` pinned to the `Slot` schema —
not something the orchestrator does inline. Two reasons: it's deterministic enough for a small model,
and keeping it out of the main loop means the orchestrator's context never fills with extraction
scaffolding.

---

## 6. Guardrails

Two mechanisms, different jobs:

**`hooks={"PreToolUse": [...]}`** — observational and blocking. Logs every tool call for the audit
trail (P9), rejects calls that violate a constitution rule (e.g. any tool call carrying a raw
`Money` float, any `search_cars` with an absent `RequirementProfile`).

**`can_use_tool` callback** — per-call policy. Returns `PermissionResultDeny` with a message the
model sees, so it adapts rather than retrying blindly.

Neither of these is what protects `confirm_booking` — that's tool visibility (P2 §4). Defence in
depth means the visibility rule is the wall and these are the alarm.

---

## 7. Demo mode

`DEMO_MODE=true` runs the complete flow — interview, research, ranking, booking, mock payment — from
canned fixtures with **no API key present**. Ported in shape from the existing Interview Agent's
`services/demo_mode.py`.

This is not a nice-to-have. Every hackathon has a venue-wifi failure or a rate limit at exactly the
wrong moment, and the team that still demos wins. **Rehearse the demo in `DEMO_MODE` at least once**
— it's checked by the P11 gate.

Fixtures live in `tests/fixtures/demo/` as recorded transcripts, so they stay in sync with the real
prompts rather than drifting into fiction.

---

## 7.1 Voice channel — deferred

A spoken interview (ElevenLabs TTS + Whisper STT) is planned but **not** part of this phase or the
hackathon demo — see [`PLAN-01-V2-ROADMAP.md` P12](PLAN-01-V2-ROADMAP.md#p12--voice-channel). It's
architected as a thin I/O layer in front of this same turn loop (transcribe → same text pipe the
`interviewer` subagent already reads; agent reply → TTS), so it drops in later without touching the
phase machine, `RequirementProfile`, or model routing above. Still Claude doing the reasoning either
way — voice only changes the transport.

---

## 8. Exit gate

`scripts/gate_phase3.py`:

| # | Criterion |
|---|---|
| 3.1 | 10 scripted personas each reach a complete `RequirementProfile` within the INTERVIEW budget |
| 3.2 | A session survives process restart: resume by `session_id` recovers phase + profile exactly |
| 3.3 | `DEMO_MODE=true` completes the full flow with `ANTHROPIC_API_KEY` **unset** |
| 3.4 | Both researcher subagents appear in the trace with overlapping timestamps (genuinely parallel) |
| 3.5 | A backward transition (new constraint mid-RECOMMEND) returns to RESEARCH and re-ranks |
| 3.6 | Every tool call appears in the `PreToolUse` audit log with session, turn, args hash |
| 3.7 | `prompts/` is the only source of prompt text — no string literal in `src/` exceeds 200 chars |
| 3.8 | Interview never emits a search before ≥2 slots are filled (asserted over the 10 personas) |

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Model jumps to results with a half-filled profile | Exit predicate is code-evaluated, not model-declared. Gate 3.8 asserts it. |
| Researchers run sequentially and nobody notices | Gate 3.4 checks timestamp overlap, not just presence. |
| Session store becomes the bottleneck | `session_store_flush="batched"`; only the phase machine's state is authoritative, transcript is append-only. |
| Long sessions blow context | Compaction `[SCALE]`; P9's budget cap is the backstop. |
| Demo fixtures drift from real prompt behaviour | Fixtures are recorded transcripts regenerated by a script, not hand-written. |
