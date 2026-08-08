# PLAN-00 — Overview

**Cardinal.** A multistep agent that interviews a car buyer or renter, researches marketplaces on
their behalf, and returns ranked recommendations it can defend — with the booking form and the
checkout rendered *inside the conversation* as MCP Apps, and every catalogue, progress view and
explanation drawn by the agent through A2UI.

Two audiences, one codebase. The hackathon needs a four-minute demo that survives a judge poking at
it. A startup needs adapters, invariants, and an audit trail. Where those diverge, this plan marks
the split explicitly: **`[MVP]`** ships for the hackathon, **`[SCALE]`** is the production depth
that follows. Under deadline, ship every `[MVP]` line and defer every `[SCALE]` line — never the
reverse.

---

## 1. The product thesis

Every car marketplace is a **filter**. You arrive knowing what you want, you narrow, you browse.
That model fails the person who doesn't know what they want yet — which is most people, most of the
time, because "should I rent or buy?" is a maths question they can't do in their head.

Cardinal is an **advisor**, not a filter. It elicits requirements the user couldn't have typed into
a search box, does the arithmetic they can't do (total cost of ownership over *their* horizon), and
defends every recommendation with numbers rather than adjectives. The transaction happens where the
conversation is, so the advice and the purchase are never separated.

Three things make that defensible rather than a chatbot wrapper:

1. **The model picks the weights; code computes the score.** Recommendations are reproducible and
   auditable. Ask "why is #2 above #3?" and there's a number, not a paragraph.
2. **Memory that outlives the session.** Preferences, rejections, and the reasoning behind past
   decisions persist and compound. The second conversation is materially better than the first.
3. **The transaction boundary is structural, not prompted.** The agent can prepare a booking; it is
   architecturally incapable of confirming one. That's the trust story, and it's enforced by tool
   visibility, not by asking the model nicely.

---

## 2. Layering

Non-negotiable, enforced by lint and by `tests/test_layer_boundary.py`:

```
src/domain/      pure Python. Models, scoring, TCO maths. No I/O, no network, no framework.
src/adapters/    marketplace adapters, embeddings, storage. Imports domain only.
src/agent/       orchestration, subagents, prompts, memory. Imports domain + adapters.
                 ⚠ NEVER imports fastapi. Must run from a plain script.
src/mcp/         MCP servers. Imports agent-facing tools; owns the ui:// resources.
src/api/         FastAPI. Transport only — routes, SSE, auth. Owns no business logic.
web/             Vite + React. A2UI renderer + MCP App host.
```

Why so strict: the agent has to be testable without a web server, and the domain has to be testable
without a model. Both of those stop being true the first time someone imports `Request` into a
scorer, and it never gets un-done afterwards.

---

## 3. System shape

```
┌──────────────────────── web/ — Vite + React 19 ────────────────────────┐
│  chat rail (plain React)  │  A2UI canvas (@a2ui/react)  │  MCP App host │
│                           │  agent-composed surfaces     │  SEP-1865     │
│                           │  catalog-validated           │  sandboxed    │
└──────────┬────────────────┴──────────────┬───────────────┴───────┬──────┘
           │ POST actions                  │ SSE: A2UI messages    │ postMessage JSON-RPC
┌──────────┴───────────────────────────────┴───────────────────────┴──────┐
│  src/api — FastAPI (transport only)                                      │
├──────────────────────────────────────────────────────────────────────────┤
│  src/agent — Claude Agent SDK orchestrator                               │
│    phase machine · subagents (interviewer/researcher×N/critic/explainer) │
│    hooks + can_use_tool guardrails · session store · memory tiers        │
├──────────────────────────────────────────────────────────────────────────┤
│  src/mcp                                                                 │
│    marketplace-mcp   search · get · availability · quote · tco           │
│    ui-mcp            render_progress · render_results · compose_surface  │
│    booking-mcp       ui://booking/form · ui://checkout/payment           │
│                      submit_draft · confirm_booking [app-only]           │
├──────────────────────────────────────────────────────────────────────────┤
│  src/adapters   MarketplaceAdapter protocol → MockDriveNow, MockAutoBazaar│
│  src/domain     Listing · RequirementProfile · Scorer · TcoEngine         │
└──────────────────────────────────────────────────────────────────────────┘
              PostgreSQL + pgvector      OpenTelemetry → Langfuse
```

---

## 4. The phase map

Ordered by dependency, not by importance. Each phase owns one capability domain and ends with a
gate you run.

| # | Phase | Owns | MVP? |
|---|---|---|---|
| **0** | [FOUNDATION](PHASE-0-FOUNDATION.md) | Contracts, layering, CI, spec-kit artifacts | ✅ |
| **1** | [INVENTORY](PHASE-1-INVENTORY.md) | Marketplace domain, adapter protocol, seeded catalogue | ✅ |
| **2** | [MCP](PHASE-2-MCP.md) | Tool protocol layer, three servers, registry manifest | ✅ |
| **3** | [AGENT](PHASE-3-AGENT.md) | Orchestration, phase machine, subagents, demo mode | ✅ |
| **4** | [MEMORY](PHASE-4-MEMORY.md) | Four tiers, consolidation, drift, forget-me | Partial |
| **5** | [REASONING](PHASE-5-REASONING.md) | Scorer, TCO, break-even, counterfactuals, grounding | ✅ |
| **6** | [GENERATIVE-UI](PHASE-6-GENERATIVE-UI.md) | A2UI catalog, compiler, transport, escape hatch | ✅ |
| **7** | [MCP-APPS](PHASE-7-MCP-APPS.md) | Host implementation, sandbox, booking form | ✅ |
| **8** | [COMMERCE](PHASE-8-COMMERCE.md) | Booking lifecycle, mock gateway, financing, idempotency | ✅ |
| **9** | [OBSERVABILITY](PHASE-9-OBSERVABILITY.md) | OTel, Langfuse, eval harness, cost governance | Bonus |
| **10** | [TRUST](PHASE-10-TRUST.md) | Injection defence, PII, tenancy, threat model | Partial |
| **11** | [DELIVERY](PHASE-11-DELIVERY.md) | Docker, deploy, CI/CD, docs, demo assets | ✅ |

**Under deadline, the order changes.** Ship: `0 → 1 → 2 → 3 → 5 → 6 → 7 → 8 → 11`, then `9`, then
backfill `4` and `10`. Phases 7 and 8 come before the bonus because MCP Apps are a *required*
deliverable; Phase 9 is explicitly a bonus and must never be traded against a required item.

---

## 5. Requirement traceability

Every line in the brief maps to exactly one phase that owns it. If a requirement has no owner, it
doesn't ship.

| Brief requirement | Owner | Gate criterion that proves it |
|---|---|---|
| Conversational interview (goal, category, budget, date) | P3 | 10 personas reach a complete profile |
| Research + rank across marketplaces, explained | P5 | Determinism + precision@3 ≥ 0.8 + groundedness |
| Form-fill flow **as an MCP App** | P7 | Cross-origin iframe + CSP + RPC audit log |
| Mock payment **as an MCP App** | P8 | State machine + idempotency + no-real-gateway scan |
| Catalogues + progress via **A2UI** | P6 | Every emitted message validates against the catalog |
| No real payments, no BMW Group APIs | P8, P10 | Static denylist scan in CI |
| ≥100 listings / ≥10 categories / ≥10 brands per category | P1 | Counts asserted and printed |
| State across interview → research → recommend | P3, P4 | Restart-resume + cross-session recall |
| Multistep agent framework | P3 | Subagent fan-out visible in the trace |
| Spec-driven development | P0 | spec-kit artifacts committed |
| Docker or public deploy | P11 | Clean clone → `docker compose up` → e2e green |
| Public repo + README | P11 | Fresh-machine run-through |
| Deck + demo video | P11 | Checked in under `docs/` |
| *Bonus:* Langfuse/Phoenix + OTel | P9 | Trace spans all phases; evals in CI |
| *Optional:* marketplace as an MCP App | P2 | Published registry manifest validates |

---

## 6. Cross-cutting decisions

Decided once here so no phase re-litigates them. Anything that changes goes in `DECISIONS.md`.

### 6.1 How the agent drives the UI

Two naive options, both wrong. *Agent emits raw A2UI JSON* — maximally generative, but an LLM
producing a valid component graph with correct data-model paths every turn will fail under demo
conditions, and it's slow. *Backend renders everything* — reliable, but it isn't agent-driven UI and
anyone who knows A2UI will see through it.

**Take the hybrid.** Semantic rendering tools (`render_progress`, `render_results`,
`render_detail`) that the backend compiles deterministically into A2UI messages against a fixed
catalog — plus one escape hatch, `compose_surface`, that accepts a real component tree from the
model and validates it server-side before forwarding. Real generative UI where novelty matters, a
reliable backbone everywhere else. Full treatment: [PHASE-6](PHASE-6-GENERATIVE-UI.md).

### 6.2 Ranking is deterministic

The model chooses **weights**; Python computes **scores**. Same profile + same seed ranks
identically, twice, forever. This is what turns "explains its reasoning" from a hallucination risk
into an auditable artifact — and it's the difference between a demo and a product a dealer would
put their name on. [PHASE-5](PHASE-5-REASONING.md).

### 6.3 Working state is code-owned, not model-owned

Slot-filling via "the model remembers" degrades under context pressure. A typed `RequirementProfile`
with per-slot value + confidence + provenance never does, and it makes the A2UI progress surface
trivially derivable. [PHASE-4](PHASE-4-MEMORY.md).

### 6.4 Marketplaces are adapters from day one

`MockDriveNow` and `MockAutoBazaar` implement the same `MarketplaceAdapter` protocol a real dealer
DMS feed or rental API would. The agent never learns which is which. This is the single most
important structural decision for the startup path — it means "connect a real marketplace" is a new
file, not a rewrite. [PHASE-1](PHASE-1-INVENTORY.md).

### 6.5 Commerce is mocked at the *gateway*, not at the *lifecycle*

The payment gateway is fake. The booking state machine, idempotency keys, audit trail, and failure
paths are real. A mock that skips the hard parts teaches you nothing and has to be rebuilt; a mock
that only replaces the network call is swapped for Stripe in an afternoon.
[PHASE-8](PHASE-8-COMMERCE.md).

### 6.6 3D is an explanation medium, not decoration

**Per-listing 3D car models do not survive into production.** Every serious used-car marketplace
uses 360° photography of the actual vehicle, because a buyer is purchasing *that* car and an
idealised render hides the wear, the wheels, and the damage they need to see. Generic archetype
models misrepresent specific listings — a consumer-protection problem, not a design choice. OEM
configurators use 3D legitimately, but only for *new* cars where the model set is finite and the
job is configuring options.

So the split:

| Surface | Mechanism | Status |
|---|---|---|
| Per-listing visual | `Vehicle360` — image-sequence turntable of the real vehicle | `[SCALE]` (stubbed with archetype GLBs for the demo, labelled "representative") |
| Powertrain explanation | `PowertrainExplainer` — 3D cutaways, **8 archetypes** (I3-T, I4 NA, I4-T, V6, V8, hybrid, PHEV, BEV skateboard) | `[MVP]` — finite, never stale, genuinely explanatory |

The engine explainer is the version of this idea worth building: it explains *why* a timing belt
means a €900 service at 100k km, or why a BEV skateboard has no transmission to fail. That's
decision-relevant information nobody presents visually, it misrepresents nothing, and the asset set
never goes stale. The agent decides when an explanation is warranted and emits the component —
which is exactly what "agent-driven dynamic interface" is supposed to mean.
[PHASE-6 §5](PHASE-6-GENERATIVE-UI.md).

### 6.7 Model routing

| Role | Model | Effort | Why |
|---|---|---|---|
| Orchestrator, critic, explainer | `claude-opus-5` | `high` / `xhigh` for ranking | Long-horizon multistep work; 1M context |
| Slot extraction (every turn) | `claude-haiku-4-5` | — | High frequency, narrow task, 5× cheaper |

`thinking={"type": "adaptive"}` plus `effort` — **not** `budget_tokens`, which returns a 400 on
Opus 5. Cost per session is budgeted and enforced in [PHASE-9](PHASE-9-OBSERVABILITY.md).

---

## 7. Stack

| Layer | Choice | Why this and not the alternative |
|---|---|---|
| Agent framework | **Claude Agent SDK (Python)** | `create_sdk_mcp_server` gives in-process MCP tools from a decorator; `agents={}` gives subagents; `session_store` gives durable state; `hooks` + `can_use_tool` give guardrails. Every brief requirement is a first-class feature rather than something to build. |
| Backend | FastAPI + Pydantic v2 | Async-native, matches the MCP Python SDK, and Pydantic models double as the tool schemas. |
| Store | PostgreSQL + pgvector | Listings, sessions, journal, and embeddings in one container. No second datastore to operate. |
| Frontend | Vite + React 19 + `@a2ui/react` | A2UI's React renderer is first-party. |
| 3D | `<model-viewer>` | One element, free lighting/shadows/orbit/AR. R3F is a stretch for a hero scene only. |
| Transport | SSE agent→client, POST client→agent | Simpler than WebSockets, survives proxies, matches A2UI's documented transports. |
| Observability | OpenTelemetry → Langfuse | One-line instrumentation for the Agent SDK; first-party integration. |
| Spec process | GitHub spec-kit | Required by the brief; the constitution step is where our invariants live. |

---

## 8. Risk register

| Risk | Severity | Mitigation | Owner |
|---|---|---|---|
| A2UI v0.9 API shifts under us | High | Pin exact versions; import from `@a2ui/react/v0_9`; wrap every call behind one adapter module so a bump touches one file | P6 |
| MCP App host is the single hardest component | High | Build it against a hardcoded HTML resource *before* wiring real booking logic. Handshake working in isolation first. | P7 |
| GLB assets blow page weight | Medium | 8 powertrain archetypes only; Draco; ≤2 MB budget enforced by a gate check; `poster` + `reveal="interaction"` | P6 |
| Live API failure during the demo | High | `DEMO_MODE=true` full canned run, no keys. **Rehearse in demo mode at least once.** | P3 |
| Cost per session unbounded in a long conversation | Medium | Token budget per session, hard cap, compaction, cheap model for extraction | P9 |
| Scope creep across twelve phases | High | One phase at a time, gate green before the next. `[SCALE]` lines are explicitly deferrable. | All |
| Accidental real-payment code path | Critical | Constitution rule + static denylist scan in CI + no payment SDK in `requirements.txt` at all | P8 |
| Prompt injection via listing text | High | Listing content wrapped as data, never instruction; adversarial corpus in CI | P10 |

---

## 9. What "done" means

A phase is done when `make gate PHASE=N` exits 0 and its real output is pasted into `PROGRESS.md`.
Not when the code looks right. Not when it worked once by hand.

The project is hackathon-done when every `[MVP]` gate is green, `docker compose up` works from a
clean clone on a machine that has never seen this repo, and the demo has been rehearsed end-to-end
in `DEMO_MODE`.

The project is product-ready when every `[SCALE]` gate is green too, the threat model in
`docs/THREAT-MODEL.md` has no open criticals, and one real marketplace adapter runs against a live
feed.

---

## 10. Beyond the hackathon

`P0`–`P11` above are the whole hackathon scope. What comes after — trade-in valuation, a real dealer
directory, dealer-facing lead scoring, voice, and the rest — is
[`PLAN-01-V2-ROADMAP.md`](PLAN-01-V2-ROADMAP.md), phases `P12`–`P17`. None of it is gated or built
yet; it exists so the next phase after P11 has somewhere to start from instead of a blank page.
