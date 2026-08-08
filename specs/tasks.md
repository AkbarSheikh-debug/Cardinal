---
description: "Task list for Cardinal MVP, grouped by phase per specs/plan.md build order"
---

# Tasks: Cardinal — MVP

**Input**: `specs/spec.md`, `specs/plan.md`, `plans/PHASE-0-FOUNDATION.md` .. `plans/PHASE-11-DELIVERY.md`

**Status source**: Checkboxes below are updated from `PROGRESS.md`, the only source of truth for
what's built (`CONSTITUTION.md` III.4). If this file and `PROGRESS.md` disagree, `PROGRESS.md` is
right — update this file to match, not the reverse.

**Organization**: Cardinal's phases are dependency-ordered, not independently-shippable user
stories (see `specs/plan.md` §Phase sequencing), so tasks are grouped by phase rather than by
`[Story]` tag. Each phase group names its exit gate (`scripts/gate_phaseN.py`) as its "done" test —
run it, don't read the code.

## Phase 0: Foundation

**Goal**: Domain contracts, repo layering, and the verification harness every later phase depends
on.

**Gate**: `make gate PHASE=0` → `scripts/gate_phase0.py`

- [x] T001 Twelve `[MVP]` Pydantic v2 domain models in `src/domain/` (`Listing`, `Money`, `Slot[T]`,
      `RequirementProfile`, `CriterionWeight`, `ScoreBreakdown`, `RankedResult`, `FieldRef`,
      `TcoEstimate`, `BookingDraft`/`Booking`, `MemoryRecord`, `DecisionEntry`), each round-tripping
      its fixture JSON (gate 0.1)
- [x] T002 `Money` rejects float construction; arithmetic preserves `Decimal` (gate 0.2)
- [x] T003 Import-boundary AST scan in `tests/test_layer_boundary.py` + matching ruff
      `flake8-tidy-imports` ban (gate 0.3)
- [x] T004 `mypy --strict src/domain` clean (gate 0.4)
- [x] T005 `scripts/gate_phase{0..11}.py` all present and runnable, all-`PENDING`-passes for
      unstarted phases (gate 0.6)
- [x] T006 Run spec-kit (`uvx --from git+https://github.com/github/spec-kit.git specify init`) and
      commit `specs/constitution.md`, `specs/spec.md`, `specs/plan.md`, `specs/tasks.md` (gate 0.5)
- [ ] T007 `[SCALE]` ADR log format and the first five ADRs (currently: `DECISIONS.md` serves this
      role in prose form; a formal ADR directory is deferred)
- [ ] T008 `[SCALE]` Semantic-versioned contract package so adapters can pin a schema version

**Checkpoint**: Gate 0 green with 0.7 correctly `PENDING` (no `prompts/` until P3 creates it).

---

## Phase 1: Inventory — ✅ done

**Goal**: Marketplace domain, adapter protocol, seeded catalogue.

**Gate**: `make gate PHASE=1` → `scripts/gate_phase1.py` — **10/10 PASS**, see `PROGRESS.md`.

- [x] T009 `MarketplaceAdapter` protocol + registry (`src/adapters/protocol.py`,
      `src/adapters/registry.py`)
- [x] T010 `MockDriveNow` (rental) and `MockAutoBazaar` (dealer) adapters, one contract suite
      parametrised over both (gates 1.3, 1.5)
- [x] T011 Catalogue generator seeding ≥100 listings, ≥10 categories, ≥10 brands per category
      (currently 240 / 12 / 12+) with deterministic, re-seedable output (gates 1.1, 1.2, 1.6)
- [x] T012 Postgres store: projected columns + canonical JSONB document, radius search filtering
      exactly in SQL (`src/adapters/db/`, D-006, D-007)
- [x] T013 Structured search returning summaries only, ≤200 tokens/item (gate 1.9)
- [x] T014 `docker compose up` → `/health` 200 with listing count (gate 1.10)
- [ ] T015 `[SCALE]` pgvector semantic search — `listing_vectors` table exists; nothing writes
      embeddings yet
- [ ] T016 `[SCALE]` freshness/TTL sweep — `withdrawn_at` exists; no sweep writes it yet
- [ ] T017 `[SCALE]` a real marketplace adapter behind a feature flag

---

## Phase 2: MCP

**Goal**: Tool protocol layer — `marketplace-mcp`, `ui-mcp`, `booking-mcp` — wrapping P1's
adapters, with `confirm_booking` structurally invisible to the model from the first commit.

**Gate**: `make gate PHASE=2` → `scripts/gate_phase2.py`

- [ ] T018 `marketplace-mcp` server exposing `search_cars`, `get_car`, `availability`, `quote`
      via `create_sdk_mcp_server`, connectable over stdio (gate 2.1)
- [ ] T019 [P] Every tool description ≥3 sentences with an explicit "call this when" clause
      (gate 2.2)
- [ ] T020 [P] Every input schema sets `additionalProperties: false` and `strict: true` (gate 2.3)
- [ ] T021 `search_cars` capped at ≤20 items / ≤4000 tokens; `get_listing` ≤800 tokens — inherits
      the `SearchPage` boundary already enforced at gate 1.9 (gates 2.4, 2.5)
- [ ] T022 `confirm_booking` declared `visibility: ["app"]` in `booking-mcp`; assert absence from
      the model's resolved toolset (gate 2.6)
- [ ] T023 In-process and stdio builds of `marketplace-mcp` return byte-identical results for a
      fixed query (gate 2.7)
- [ ] T024 `[SCALE]` registry manifest validates against the MCP registry schema (gate 2.8)

**Checkpoint**: A model connected via MCP Inspector can search and get listings; it cannot see a
booking-confirmation tool under any circumstance.

---

## Phase 3: Agent

**Goal**: Claude Agent SDK orchestration — phase machine, interviewer/researcher×N/critic/explainer
subagents, `DEMO_MODE`.

**Gate**: `make gate PHASE=3` → `scripts/gate_phase3.py`

- [ ] T025 Phase machine (INTERVIEW → RESEARCH → RECOMMEND → BOOK) with a durable `session_store`
      surviving process restart (gate 3.2)
- [ ] T026 Interviewer subagent driving `RequirementProfile` slot-filling; never emits a search
      before ≥2 slots are filled (gate 3.8)
- [ ] T027 10 scripted personas each reach a complete profile within the interview budget
      (gate 3.1)
- [ ] T028 Two researcher subagents fanning out genuinely in parallel — overlapping timestamps in
      the trace (gate 3.4)
- [ ] T029 Backward transition: a new constraint mid-RECOMMEND returns to RESEARCH and re-ranks
      (gate 3.5)
- [ ] T030 `PreToolUse` hook logging every tool call with session, turn, args hash (gate 3.6)
- [ ] T031 All prompts as `.md` files under `prompts/`; no string literal in `src/` over 200 chars
      (gate 3.7 — this is also gate 0.7, which starts asserting the moment `prompts/` exists)
- [ ] T032 `DEMO_MODE=true` completes the full flow with `ANTHROPIC_API_KEY` unset (gate 3.3)

**Checkpoint**: A full interview-to-shortlist conversation runs, resumably, in demo mode with zero
keys.

---

## Phase 5: Reasoning

**Goal**: Deterministic scorer, TCO engine, grounding validator. (P4 Memory is deferred past this
point per `specs/plan.md`'s build order — its `[MVP]` slice is already exercised by T025.)

**Gate**: `make gate PHASE=5` → `scripts/gate_phase5.py`

- [ ] T033 `src/domain/scoring.py` — model supplies `CriterionWeight`s, code computes
      `ScoreBreakdown`; zero imports outside stdlib + pydantic (gate 5.9)
- [ ] T034 Determinism: same profile + seed, two runs, byte-identical ranking (gate 5.1)
- [ ] T035 `ScoreBreakdown` contributions sum to the total within 1e-9 (gate 5.2)
- [ ] T036 Hard filters exclude — never merely deprioritize — violating listings at every rank
      (gate 5.3)
- [ ] T037 Groundedness validator rejects a deliberately fabricated statistic (gate 5.5)
- [ ] T038 TCO engine: break-even for a known fixture matches a hand-computed value within €50;
      rental pricing applies weekly tiers, not `daily × 7` (gates 5.6, 5.7)
- [ ] T039 Critic subagent catches a seeded violation (listing available after target date) before
      render (gate 5.8)
- [ ] T040 Golden set of 20 personas: precision@3 ≥ 0.8 (gate 5.4)
- [ ] T041 `[SCALE]` counterfactual solver returns ≥2 relaxation options on a seeded zero-result
      query (gate 5.10)

**Checkpoint**: Every ranked result's rationale is auditable back to a listing field and a weight.

---

## Phase 6: Generative UI

**Goal**: A2UI catalog + deterministic compiler (`render_progress`, `render_results`,
`render_detail`) plus the `compose_surface` escape hatch, validated server-side.

**Gate**: `make gate PHASE=6` → `scripts/gate_phase6.py`

- [ ] T042 Component catalog + compiler; every compiled message validates against it (gate 6.1)
- [ ] T043 `compose_surface` rejects unknown components, dangling child refs, duplicate ids, and
      depth > 8, returning the error to the model as a tool result — nothing partial forwarded
      (gates 6.3, 6.4)
- [ ] T044 Golden-message fixtures render in a headless browser with zero console errors
      (gate 6.2)
- [ ] T045 Action round-trip: a simulated click reaches the agent session with full provenance
      (gate 6.5)
- [ ] T046 Surface identity is stable — a repeated `render_results` updates in place (gate 6.6)
- [ ] T047 8 powertrain-archetype GLBs (I3-T, I4 NA, I4-T, V6, V8, hybrid, PHEV, BEV skateboard),
      each ≤2 MB, total bundle ≤16 MB, every `<model-viewer>` with a `poster` (gates 6.7, 6.8)
- [ ] T048 `[SCALE]` reduced-motion honoured; visible focus state on every interactive element
      (gate 6.10)

**Checkpoint**: The agent can compose real UI through one validated path; the powertrain explainer
renders for at least one seeded listing per archetype.

---

## Phase 7: MCP Apps

**Goal**: The sandboxed host that P6's escape hatch and P8's booking flow both render inside.

**Gate**: `make gate PHASE=7` → `scripts/gate_phase7.py`

- [ ] T049 Host renders a hardcoded HTML resource in a cross-origin iframe before any real booking
      logic is wired — isolate the handshake first (gates 7.1, per PLAN-00 §8 risk register)
- [ ] T050 CSP on the inner document matches the resource's `_meta.ui.csp`; undeclared
      `connect-src` fetch fails and logs `blocked` (gates 7.2, 7.3, 7.10)
- [ ] T051 `ui/initialize` handshake; `hostContext.theme` reaches and visibly applies in the App
      (gate 7.4)
- [ ] T052 `ui/notifications/tool-input` delivers pre-fill exactly once, after init (gate 7.5)
- [ ] T053 All `tools/call` from the view routed through the host proxy — direct view→server
      traffic asserted impossible by network trace (gate 7.6)
- [ ] T054 `ui/resource-teardown` releases the iframe and listeners; no leak across 20 open/close
      cycles (gate 7.7)
- [ ] T055 `size-changed` resizes without layout shift in the surrounding A2UI surface (gate 7.8)
- [ ] T056 Audit log has one entry per view-initiated RPC, no gaps, across a full booking flow
      (gate 7.9)

**Checkpoint**: The booking form (`ui://booking/form`) renders inside the sandbox end to end.

---

## Phase 8: Commerce

**Goal**: Booking lifecycle state machine, mock payment gateway, idempotency, audit trail.

**Gate**: `make gate PHASE=8` → `scripts/gate_phase8.py`

- [ ] T057 Booking state machine: every `(state, event)` pair transitions or explicitly rejects —
      no silent no-ops (gate 8.1)
- [ ] T058 `confirm_booking` absent from the resolved toolset (asserted from SDK state, not config)
      (gate 8.2)
- [ ] T059 Playwright drives a full session; assert zero agent-initiated `confirm_booking` calls
      (gate 8.3)
- [ ] T060 `confirm_booking` without a valid `gesture_token` is rejected (gate 8.4)
- [ ] T061 Double-submit with the same idempotency key produces one booking, two identical
      responses (gate 8.5)
- [ ] T062 Every decline/error/timeout test card renders a distinct, non-spinner UI state
      (gate 8.6)
- [ ] T063 Static denylist scan: zero payment-provider identifiers in source, deps, lockfiles
      (gate 8.7)
- [ ] T064 No card number in any log, trace, DB row, or audit entry — scan asserts it (gate 8.8)
- [ ] T065 `MOCK — NO REAL PAYMENT` banner present and above the fold (gate 8.10)
- [ ] T066 `PENDING` older than TTL transitions to `EXPIRED` and releases the listing (gate 8.9)
- [ ] T067 Client-computed monthly payment matches server recomputation to the cent (gate 8.11)
- [ ] T068 Audit trail: one entry per transition, actor + timestamps + gesture provenance
      (gate 8.12)

**Checkpoint**: A user can go from shortlist to a confirmed mock booking, and the transcript proves
the agent never could have done it alone.

---

## Phase 11: Delivery

**Goal**: Everything above, packaged for a judge on a machine that has never seen the repo.

**Gate**: `make gate PHASE=11` → `scripts/gate_phase11.py`

- [ ] T069 Clean clone → `docker compose up` → all services healthy within 120s (gate 11.1)
- [ ] T070 Seed runs automatically; `/health` reports ≥100 listings (gate 11.2)
- [ ] T071 Playwright e2e walks all seven demo beats, screenshotting each (gate 11.3)
- [ ] T072 e2e passes with the entire environment unset except `DEMO_MODE=true` (gate 11.4)
- [ ] T073 `booking` service resolves on a distinct hostname from `web` (gate 11.5)
- [ ] T074 Every image runs as non-root; none exceeds 800 MB (gate 11.6)
- [ ] T075 `.env.example` covers every variable read anywhere in the codebase (gate 11.7)
- [ ] T076 README run instructions executed verbatim by someone who didn't write them (gate 11.8)
- [ ] T077 Deck and demo video checked in under `docs/` (gate 11.9)
- [ ] T078 `make verify` green across every gate 0–11 (gate 11.10)
- [ ] T079 `[SCALE]` public deployment reachable and healthy (gate 11.11)

**Checkpoint**: Hackathon-done — every `[MVP]` gate green, demo rehearsed in `DEMO_MODE`.

---

## Phase 9: Observability *(bonus — never traded against a required item)*

**Goal**: OTel spans across every phase, Langfuse export, eval harness, cost governance.

**Gate**: `make gate PHASE=9` → `scripts/gate_phase9.py`

- [ ] T080 One trace per session containing spans for all four phases; every MCP tool call a span
      with args hash and duration (gates 9.1, 9.2)
- [ ] T081 Both researcher subagents appear as sibling spans with overlapping ranges (gate 9.3)
- [ ] T082 Eval harness runs 30 personas headless, scored report, zero guardrail violations
      (gates 9.4, 9.5)
- [ ] T083 Redaction hook scanned against a real span export — zero PII (gate 9.6)
- [ ] T084 Cost per session ≤ $0.40 across the golden set, reported per role (gate 9.7)
- [ ] T085 `[SCALE]` prompt-cache hit rate > 0 across repeated sessions; eval regression > 5%
      fails CI (gates 9.8, 9.9)

---

## Phase 4: Memory *(backfilled after the required path is green)*

**Goal**: Four memory tiers, consolidation, drift detection, `forget_me`.

**Gate**: `make gate PHASE=4` → `scripts/gate_phase4.py`

- [ ] T086 `[MVP]` `RequirementProfile` survives process restart with confidence/source_turn intact
      — largely exercised by T025; confirm gate 4.1 passes standalone
- [ ] T087 `[MVP]` A `locked` slot is not overwritten by a later low-confidence inference (gate 4.2)
- [ ] T088 `[MVP]` Journal answers "why A over B" from a recorded row, zero model calls, byte-
      identical to the original rationale (gate 4.3)
- [ ] T089 `[SCALE]` Second session for a known user recalls ≥1 prior constraint unprompted
      (gate 4.4)
- [ ] T090 `[SCALE]` Contradicting memory sets `superseded_by`; recall returns the newer (gate 4.5)
- [ ] T091 `[SCALE]` Memory index for 50 memories ≤800 tokens (gate 4.6)
- [ ] T092 `[SCALE]` Drift detector fires on scripted divergence, produces a question not an update
      (gate 4.7)
- [ ] T093 `[SCALE]` `forget_me` leaves zero rows across all four stores + Langfuse (gate 4.8)

---

## Phase 10: Trust *(backfilled after the required path is green)*

**Goal**: Injection defence, PII scanning, tenancy isolation, threat model.

**Gate**: `make gate PHASE=10` → `scripts/gate_phase10.py`

- [ ] T094 `[MVP]` ~30-case injection corpus against listing content: zero successes (gate 10.1)
- [ ] T095 `[MVP]` A memory-poisoning attempt does not write to episodic memory (gate 10.2)
- [ ] T096 `[MVP]` Denylist scan: zero hits across source, deps, lockfiles (gate 10.3)
- [ ] T097 `[MVP]` Listing text reaches the model wrapped and labelled `trust="untrusted"`
      (gate 10.4)
- [ ] T098 `[SCALE]` PII scan over logs + a real span export: zero findings (gate 10.5)
- [ ] T099 `[SCALE]` Two-tenant isolation: zero cross-visibility across all stores incl. vector
      search (gate 10.6)
- [ ] T100 `[SCALE]` `pip-audit` + `npm audit`: no high/critical (gate 10.7)
- [ ] T101 `[SCALE]` Every 3D asset has an attribution entry (gate 10.8)
- [ ] T102 `[SCALE]` `docs/THREAT-MODEL.md` exists with no open criticals (gate 10.9)

---

## Dependencies & Execution Order

- **Phase 0 → Phase 1**: contracts and layering before anything is seeded (already true, D-010).
- **Phase 1 → Phase 2**: adapters must exist before tools can wrap them.
- **Phase 2 → Phase 3**: tools must exist before an orchestrator can call them.
- **Phase 3 → Phase 5**: a phase machine must exist before there's a RECOMMEND phase to rank in.
- **Phase 5 → Phase 6**: `RankedResult` must exist before there's anything to render.
- **Phase 6 → Phase 7**: the A2UI escape hatch (`compose_surface`) and the MCP App host are
  independent enough to build in parallel, but Phase 7's booking form needs Phase 6's surface
  transport to sit inside.
- **Phase 7 → Phase 8**: the sandbox must exist before booking/payment forms render inside it.
- **Phase 8 → Phase 11**: nothing ships until the full flow — including commerce — is real.
- **Phase 9, 4, 10**: each depends only on Phase 3/5/8 respectively being done; they do not block
  Phase 11 and are explicitly sequenced after it under deadline (`plans/PLAN-00-OVERVIEW.md` §4).

### Parallel opportunities within a phase

Tasks marked `[P]` touch different files with no dependency on each other and can be done in
parallel once their phase's foundational task is complete (e.g. T019/T020 in Phase 2).

## Implementation Strategy

**MVP-critical path**: P0 → P1 (done) → P2 → P3 → P5 → P6 → P7 → P8 → P11. Stop and run
`make gate PHASE=N` at each arrow before starting the next phase's code (`CONSTITUTION.md` III.2).
Backfill P9 → P4 → P10 only once that path is fully green, per `plans/PLAN-00-OVERVIEW.md` §4 —
P9 is a bonus and must never be traded against a required item.
