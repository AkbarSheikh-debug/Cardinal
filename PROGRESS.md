# Progress

The only source of truth for what exists (CONSTITUTION III.4). The plan docs describe *intent* and
are deliberately not kept in sync with this file. If it isn't here, it isn't built.

A phase is done when `make gate PHASE=N` prints green and its **real output** is pasted below —
never "the code looks right" (CONSTITUTION III.1).

| Phase | State | Gate |
|---|---|---|
| **0 — FOUNDATION** | ✅ **Done** | **7/7 PASS** |
| **1 — INVENTORY** | ✅ **Done** | **10/10 PASS** |
| **2 — MCP** | ✅ **Done** — registry manifest deferred, `[SCALE]` | **7 PASS, 1 PENDING** |
| **3 — AGENT** | ✅ **Done** | **8/8 PASS** |
| **4 — MEMORY** | Partial — `[MVP]` done, `[SCALE]` deferred | **3 PASS, 5 PENDING** |
| **5 — REASONING** | `[MVP]` done, `[SCALE]` deferred | **9 PASS, 1 PENDING** |
| **6 — GENERATIVE-UI** | `[MVP]` done, `[SCALE]` deferred | **9 PASS, 1 PENDING** |
| **7 — MCP-APPS** | ✅ **Done** | **10/10 PASS** |
| **8 — COMMERCE** | ✅ **Done** | **12/12 PASS** |
| **9 — OBSERVABILITY** | `[MVP-bonus]` done, `[SCALE]` deferred | **7 PASS, 2 PENDING** |
| **10 — TRUST** | `[MVP]` done, `[SCALE]` deferred | **4 PASS, 5 PENDING** |
| **11 — DELIVERY** | `[MVP]` done, `[SCALE]` deferred | **8 PASS, 3 PENDING** |

---

## Phase 1 — Inventory ✅

Run on 2026-08-07 with the stack up (`docker compose up`), against Postgres 16 + pgvector.

```
==============================================================================
GATE 1 -- Inventory -- adapter protocol, seeded catalogue, structured search
==============================================================================
  1.1    PASS     >=100 listings (target 240)
           240 listings generated
  1.2    PASS     >=10 distinct categories (target 12)
           12 categories: convertible, coupe, crossover, electric, hatchback, luxury,
           pickup, sedan, sports, suv, van_mpv, wagon
  1.3    PASS     >=10 distinct brands within EVERY category
           ok  convertible  12 brands
           ok  coupe        12 brands
           ok  crossover    14 brands
           ok  electric     11 brands
           ok  hatchback    12 brands
           ok  luxury       12 brands
           ok  pickup       13 brands
           ok  sedan        12 brands
           ok  sports       12 brands
           ok  suv          12 brands
           ok  van_mpv      12 brands
           ok  wagon        12 brands
  1.4    PASS     both rent and buy present, each >=40
           buyable=150 rentable=110 (buy=130 rent=90 both=20)
  1.5    PASS     adapter contract suite passes against every adapter
           60 passed, 3 skipped in 0.10s
           parametrised over: mock_autobazaar, mock_drivenow
  1.6    PASS     two seed runs with the same seed are byte-identical
           sha256 54919b48db4cd9352ef3af816466db9e... identical across two processes
  1.7    PASS     every Listing validates; raw non-empty on all rows
           240/240 rows validate and round-trip; raw non-empty
  1.8    PASS     price/mileage/year correlation holds (no listing >2 sigma)
           max |z| = 1.731 (limit 2.0) on AB-1073 2019 Peugeot 2008
           pearson r(actual, model) = 0.9981 across 240 rows
  1.9    PASS     search returns summaries only, <=200 tokens each
           max summary 117 tokens, mean 105.3 (cap 200); a full record would be ~435 tokens
  1.10   PASS     docker compose up -> /health 200 with a listing count
           200 OK from http://localhost:8000/health
           backend=postgres listings=240 sources={'mock_autobazaar': 130, 'mock_drivenow': 110}
------------------------------------------------------------------------------
  10 passed, 0 failed, 0 pending
  GATE 1 GREEN
==============================================================================
```

Criterion 1.10 reports `PENDING` rather than `PASS` when no stack is running, so `make verify` works
on a machine with no Docker. Run `python -m scripts.gate_phase1 --require-stack` to make it a hard
failure, which is how the output above was produced.

### What shipped

| Area | Files |
|---|---|
| Adapter protocol | `src/adapters/protocol.py`, `src/adapters/registry.py` |
| Mock marketplaces | `src/adapters/mock/{base,drivenow,autobazaar}.py` |
| Catalogue generator | `src/adapters/catalogue/{taxonomy,generator}.py` |
| Retrieval semantics | `src/adapters/filtering.py`, `src/adapters/store.py` |
| Postgres | `src/adapters/db/*`, `migrations/versions/0001_initial_schema.py` |
| Seed | `scripts/seed_marketplace.py` |
| Transport | `src/api/main.py` (`/health`, `/adapters`), `Dockerfile`, `docker-compose.yml` |
| Tests | `tests/contract/` (60), `tests/unit/` (63), `tests/integration/` (26) |

`MockDriveNow` carries all 90 `rent` plus all 20 `both` listings; `MockAutoBazaar` carries the 130
`buy`. A rental marketplace that also sells its ex-fleet cars is a real business model, and it puts
every dual-offer listing on the adapter whose `availability` actually means something.

### Deferred, deliberately

- **`[SCALE]` pgvector semantic search.** The `listing_vectors` table and the `vector(768)` column
  exist and the extension is enabled; nothing writes embeddings. Structured search alone is enough
  for the hackathon (PHASE-1 §8), and enabling this later is a backfill, not a migration.
- **`[SCALE]` freshness/TTL and the staleness sweep.** `withdrawn_at` exists and every query
  excludes withdrawn rows; no sweep writes it yet.
- **`[SCALE]` a real adapter behind a feature flag.**

---

## Phase 2 — MCP ✅

Run on 2026-08-08, no container needed — every criterion is pure Python against an in-memory
catalogue plus a subprocess for the stdio checks.

```
==============================================================================
GATE 2 -- MCP -- Tool protocol layer, three servers, registry manifest
==============================================================================
  2.1    PASS     MCP Inspector connects to marketplace-mcp over stdio and lists all five tools
           connected over stdio, tools/list -> ['check_availability', 'compare_listings', 'get_listing', 'get_quote', 'search_cars']
  2.2    PASS     every tool description >=3 sentences with an explicit "call this when" clause
           14/14 tools carry a >=3-sentence prescriptive description
  2.3    PASS     every input schema sets additionalProperties: false and strict: true
           14/14 schemas set additionalProperties=false, strict=true
  2.4    PASS     search_cars result for the broadest query is <=20 items, <=4000 tokens
           20 items, total=240, 2338 tokens (cap 4000)
  2.5    PASS     get_listing result is <=800 tokens
           327 tokens (cap 800)
  2.6    PASS     confirm_booking is absent from the tool list presented to the model
           model-facing booking-mcp resolves to ('open_booking_form', 'open_checkout') (no confirm_booking, no submit_booking_draft)
           app-facing booking-mcp resolves to ('open_booking_form', 'open_checkout', 'submit_booking_draft', 'confirm_booking') (both present) -- resolved via the SDK's own Server.request_handlers, not read from config
  2.7    PASS     in-process and stdio builds of marketplace-mcp return byte-identical results
           identical 2417-byte result for {'categories': ['suv'], 'sort': 'price_asc', 'page_size': 5} across both transports
  2.8    PENDING  [SCALE] registry manifest validates against the registry schema
           not built -- marketplace-mcp registry submission is [SCALE] (PHASE-2 §7)
------------------------------------------------------------------------------
  7 passed, 0 failed, 1 pending
  GATE 2 GREEN (with 1 pending)
==============================================================================
```

Criterion 2.1 talks to the standalone stdio server over the real MCP JSON-RPC wire protocol via
`mcp.client.stdio` -- the programmatic equivalent of what MCP Inspector's UI does, since Inspector
itself has no CLI mode to script in CI. Criterion 2.6 is asserted the way PHASE-2 §8 insists on:
against the SDK's own `Server.request_handlers[ListToolsRequest]`, not against this project's own
`audience` bookkeeping read back to itself.

### What shipped

| Area | Files |
|---|---|
| Visibility mechanism | `src/mcp/audience.py` (`ToolSpec`, `for_audience`, `resolved_tool_names`) |
| Schema helper | `src/mcp/schema.py` (`strict_schema`, `enum_property`, `enum_array_property`) |
| `marketplace-mcp` | `src/mcp/marketplace/{tools,server,stdio}.py` -- 5 tools, real handlers over P1's `ListingStore`/adapters, in-process + stdio |
| `ui-mcp` | `src/mcp/ui/{tools,server}.py` -- 5 tools, schemas frozen, handlers stub to a labelled P6 non-implementation |
| `booking-mcp` | `src/mcp/booking/{tools,server,http}.py` -- 4 tools, schemas frozen, handlers stub to a labelled P7/P8 non-implementation; `confirm_booking` and `submit_booking_draft` carry `audience=("app",)` |
| Gate | `scripts/gate_phase2.py` |
| Tests | `tests/unit/test_mcp_{marketplace,ui,booking,audience}.py` (25) |

`search_cars` and `compare_listings` query across every registered marketplace at once via
`ListingStore.query(sources=registered_source_names())` rather than one adapter at a time -- the
model never learns marketplaces are plural, per CONSTITUTION II.6. `check_availability` and
`get_quote` route through `adapter_by_name` once a `source` is known, since pricing and booking
logic are genuinely adapter-specific.

`confirm_booking`'s invisibility (CONSTITUTION I.2) is enforced by construction, not by a
permission check: `audience=("app",)` means it is never passed into `create_sdk_mcp_server` when
building the model-facing `booking-mcp` config, so there is no tool for a permission callback to
guard in the first place. The same tool is fully present and callable on an `audience="app"`
build, proving the absence is deliberate rather than an unfinished implementation.

### Deferred, deliberately

- **`[SCALE]` Official MCP Registry manifest + submission (gate 2.8).** `marketplace-mcp`'s
  standalone stdio transport works today (gates 2.1, 2.7); writing and submitting the manifest is
  PHASE-2 §7's explicit `[SCALE]` line.
- **`[SCALE]` tool-level auth scopes for multi-tenant use.**
- **`booking-mcp`'s HTTP transport (`src/mcp/booking/http.py`) is wired but unexercised by any
  gate.** No `ui://` resource exists to serve yet -- that is P7's job. The module builds a real
  `StreamableHTTPSessionManager`-backed Starlette app today so P7 has a working transport to attach
  resources to rather than a transport to invent.

---

## Phase 3 — Agent ✅

Run on 2026-08-08 against live Postgres (`docker compose up -d postgres`, migrations already at
head from Phase 1's run) with `--require-stack`, so 3.2 is a hard PASS rather than PENDING.

```
==============================================================================
GATE 3 -- AGENT -- Orchestration, phase machine, subagents, demo mode
==============================================================================
  3.1    PASS     10 scripted personas each reach a complete RequirementProfile within budget
           Efficient Erik: complete in 1 turn(s)
           Renting Rita: complete in 3 turn(s)
           Family Fatima: complete in 4 turn(s)
           Sports Sam: complete in 2 turn(s)
           Electric Emma: complete in 3 turn(s)
           Wagon Will: complete in 4 turn(s)
           Luxury Liam: complete in 1 turn(s)
           Pickup Priya: complete in 3 turn(s)
           Convertible Carlos: complete in 3 turn(s)
           City Chloe: complete in 3 turn(s)
  3.2    PASS     a session survives process restart: resume by session_id recovers state exactly
           save -> load through a fresh store instance recovered phase + profile exactly
  3.3    PASS     DEMO_MODE=true completes the full flow with ANTHROPIC_API_KEY unset
           persona 'Efficient Erik' reached transact (booking_status='draft_submitted') with no ANTHROPIC_API_KEY set
  3.4    PASS     both researcher subagents appear in the trace with overlapping timestamps
           2 researchers, overlapping spans: mock_autobazaar=[36953.9439, 36953.9728], mock_drivenow=[36953.9439, 36953.9729]
  3.5    PASS     a backward transition mid-RECOMMEND returns to RESEARCH and re-ranks
           'Efficient Erik' + 'Actually, make it under 15000 euros' mid-RECOMMEND -> RESEARCH visited 2x; final phase transact
  3.6    PASS     every tool call appears in the PreToolUse audit log with session, turn, args hash
           4 tool calls audited, each with session id, turn, sha256 args hash
  3.7    PASS     prompts/ is the only source of prompt text -- no src/ literal exceeds 200 chars
           6 prompt files: critic.md, explainer.md, interviewer.md, orchestrator_system.md, researcher.md, slot_extraction.md; no long literal in src/
  3.8    PASS     interview never emits a search before >=2 slots are filled (over the 10 personas)
           10/10 personas: search_gate never had to deny a search_cars call (see tests/unit/test_agent_guardrails.py for the gate denying an under-filled profile directly)
------------------------------------------------------------------------------
  8 passed, 0 failed, 0 pending
  GATE 3 GREEN
==============================================================================
```

Without a database up, 3.2 reports `PENDING` rather than `PASS` (same convention as 1.10) — run
`python -m scripts.gate_phase3 --require-stack` to make it a hard failure.

Every other criterion runs with **no `ANTHROPIC_API_KEY` and no live `ClaudeSDKClient` session** —
see DECISIONS.md D-015 for why the gate is built entirely on `DEMO_MODE`'s deterministic path
rather than a live subprocess against the `claude` CLI, the same reasoning D-012 already
established for gate 2.6.

### What shipped

| Area | Files |
|---|---|
| Phase machine | `src/agent/phase_machine.py` — `Phase`, `SessionState`, turn budgets, exit predicates, `apply_profile_update`'s backward transition |
| Slot extraction | `src/agent/extraction.py` — `DemoSlotExtractor` (regex/keyword, offline) and `ModelSlotExtractor` (`claude-haiku-4-5`, live) behind one `SlotExtractor` protocol |
| Turn processing | `src/agent/interview.py` — the one `process_turn` both `demo.py` and `orchestrator.py` call through |
| Concurrent research | `src/agent/research.py` — `dispatch_researchers` fans out over `registered_source_names()` via `asyncio.gather` against the real `ListingStore` |
| Guardrails | `src/agent/guardrails.py` — `PreToolUse` audit hook (`AuditLog`, gate 3.6) + `can_use_tool` search-gate (gate 3.8) |
| Subagent roster | `src/agent/subagents.py` — `interviewer`/`researcher`/`critic`/`explainer` `AgentDefinition`s, prompts loaded from `prompts/` |
| Session durability | `src/agent/session_store.py` — `PostgresSessionStateStore` (reuses P0's `sessions` table, D-014) + `InMemorySessionStateStore` |
| Demo mode | `src/agent/demo.py` — `run_demo_session`, the full INTERVIEW→RESEARCH→RECOMMEND→TRANSACT flow with no SDK involved |
| Live orchestration | `src/agent/orchestrator.py` — real `ClaudeAgentOptions` wiring (`mcp_servers`, `agents`, `hooks`, `can_use_tool`, model routing); gate-unexercised by design (D-015) |
| Prompts | `prompts/{orchestrator_system,interviewer,researcher,critic,explainer,slot_extraction}.md` |
| Gate | `scripts/gate_phase3.py` |
| Fixtures | `tests/fixtures/demo/personas.json` — 10 scripted personas |
| Tests | `tests/unit/test_agent_{phase_machine,extraction,guardrails,demo,prompts}.py` (66), `tests/integration/test_agent_session_store_postgres.py` (4) |

`src/agent` joined `tests/test_layer_boundary.py`'s `REQUIRED_LAYERS` (alongside `mcp`, which had
been live since P2 but wasn't added at the time). The Makefile's `typecheck` target now runs
`mypy src/agent` separately from `mypy --strict src/domain` rather than folding both under one
`--strict` invocation — `src/agent` legitimately imports `src/adapters`, and a combined `--strict`
call was transitively strict-checking (and failing on) not-yet-strict adapters code it followed
through that import. `src/agent` is held to the same bar via pyproject's per-module override
instead.

### Deferred, deliberately

- **`[SCALE]` Interrupt / steering mid-turn.**
- **`[SCALE]` Compaction strategy for very long sessions.**
- **`[SCALE]` Multi-provider fallback when the primary API rate-limits.**
- **A live rehearsal of `orchestrator.py` against the real `claude` CLI.** The wiring is real,
  type-checked and imports cleanly; nobody has yet run it end-to-end with a live model. PHASE-3 §7
  says to rehearse `DEMO_MODE` at least once before a real demo, not the live path, but a live
  rehearsal is still worth doing before this is called demo-ready in the fuller sense.

---

## Phase 4 — Memory (partial)

Run on 2026-08-08 against live Postgres (`docker compose up -d postgres`) with `--require-stack`,
so 4.1 is a hard PASS rather than PENDING.

```
==============================================================================
GATE 4 -- MEMORY -- Four tiers, consolidation, drift, forget-me
==============================================================================
  4.1    PASS     profile survives process restart; every slot's confidence/source_turn intact
           save -> load through a fresh store instance kept every slot's confidence and source_turn
  4.2    PASS     a locked slot is not modified by a later low-confidence inference
           turn-1 locked budget (EUR 28000) survived a turn-9 confidence-0.4 inference of EUR 45000 unchanged; the unlocked category slot in the same turn did update
  4.3    PASS     journal answers 'why rank A over B' from a recorded row, zero model calls
           explain() returned the recorded rationale for 'mock_autobazaar:AB-1034' byte-identical to the row `_record_recommendation` wrote, with ANTHROPIC_API_KEY unset (604 chars, inputs_hash=25a4d431be97...)
  4.4    PENDING  [SCALE] second session for a known user recalls >=1 prior constraint unprompted
           episodic memory (remember/recall tool, MEMORY.md index) not built -- [SCALE]
  4.5    PENDING  [SCALE] contradicting memory sets superseded_by; recall returns the newer
           contradiction handling over MemoryRecord.superseded_by not built -- [SCALE]
  4.6    PENDING  [SCALE] memory index for 50 memories is <=800 tokens
           MEMORY.md-style progressive-disclosure index not built -- [SCALE]
  4.7    PENDING  [SCALE] drift detector fires on a scripted divergence, asks a question
           preference-drift detector over the interaction log not built -- [SCALE]
  4.8    PENDING  [SCALE] forget_me leaves zero rows across all four stores + Langfuse
           forget_me erasure path not built -- [SCALE]; Langfuse itself is P9's
------------------------------------------------------------------------------
  3 passed, 0 failed, 5 pending
  GATE 4 GREEN (with 5 pending)
==============================================================================
```

Without a database up, 4.1 reports `PENDING` rather than `PASS` (same convention as 1.10/3.2) --
run `python -m scripts.gate_phase4 --require-stack` to make it a hard failure. 4.2 and 4.3 are pure
Python and always run regardless of the stack.

Built now, ahead of PLAN-00 §4's suggested backfill-last order, because P4's `[MVP]` scope only
needs P0 (`RequirementProfile`) and P3 (`SessionState`, turn processing) -- both already green --
and CONSTITUTION III.2 blocks starting a phase before the *previous* one's gate is green, not
building phases out of the suggested shipping sequence. See DECISIONS.md D-019.

### What shipped

| Area | Files |
|---|---|
| Decision journal | `src/agent/journal.py` -- `DecisionJournal` protocol, `InMemoryDecisionJournal`, `PostgresDecisionJournal` (reuses the `decisions` table P0 pre-created), `explain()`, `compute_inputs_hash()`, `session_uuid()` |
| Journal wired into RECOMMEND | `src/agent/demo.py`'s `_record_recommendation` writes one `DecisionEntry` per recommendation, with a rationale honest about P3's placeholder pick logic (D-019) |
| Gate | `scripts/gate_phase4.py` |
| Tests | `tests/unit/test_agent_journal.py` (13, includes domain-level locked-slot coverage), `tests/integration/test_agent_journal_postgres.py` (4) |

Working state (4.1, 4.2) needed no new production code: `RequirementProfile`/`Slot.fill`'s
locked-slot guard is P0's, and `PostgresSessionStateStore`'s restart-resume is P3's (gate 3.2)
-- PHASE-4 §3.1 and PHASE-3 §8 gate 3.2 describe the same code-owned mechanism from two angles on
purpose. Gate 4.1/4.2 assert it explicitly under the Phase 4 label rather than silently relying on
Phase 3 having already proven it.

### Deferred, deliberately

- **`[SCALE]` Episodic memory** (`remember`/`recall` tool, markdown + frontmatter, `MEMORY.md`
  index) -- gate 4.4, 4.6.
- **`[SCALE]` Semantic retrieval** over listings and past decisions (pgvector) -- not gated
  directly, but a prerequisite PLAN-00 §4 also defers.
- **`[SCALE]` Consolidation, contradiction detection (`MemoryRecord.superseded_by`), staleness
  sweep** -- gate 4.5.
- **`[SCALE]` Preference-drift detection** -- gate 4.7.
- **`[SCALE]` `forget_me` erasure** across all four stores + Langfuse -- gate 4.8. `MemoryRow`
  exists in the schema (P0/P1) but nothing writes to it yet, so there is nothing to erase from
  that store today; the other three (`decisions`, `sessions`, vectors) would need the same
  treatment once P9's Langfuse integration exists to erase from too.

---

## Phase 5 — Reasoning ✅

Run on 2026-08-08, no container needed — every criterion is pure/deterministic code
(CONSTITUTION II.2), the same reasoning D-015 already established for gate 3.

```
==============================================================================
GATE 5 -- REASONING -- scoring, TCO, grounding, critic pass
==============================================================================
  5.1    PASS     Determinism: same profile + seed, two runs, byte-identical
           15 candidates ranked, byte-identical across two runs
  5.2    PASS     ScoreBreakdown contributions sum to the total within 1e-9
           total=0.690000, sum(contributions)=0.690000
  5.3    PASS     Hard filters remove rows -- no filtered listing appears at any rank
           96000 km listing excluded by a lte-80000 hard filter; 1/2 candidates survived
  5.4    PASS     Golden set of 20 personas: precision@3 >= 0.8 vs stated constraints
           19/20 personas feasible, 1 infeasible (a real answer, not a missing one); mean
           precision@3=1.000; worst persona 'Golden 01 - Budget Hatchback Buyer'
           precision@3=1.00
  5.5    PASS     Groundedness validator rejects a deliberately fabricated statistic
           999% fabricated claim rejected; genuine 80% claim (curve[0]=0.80) accepted
  5.6    PASS     TCO: break-even for a known fixture matches a hand-computed value
           break_even_month=5 (hand-derived from Buy(h)=370+543.25h, Rent(h)=631.25h);
           buy(5)=EUR 3086.25 (hand: 3086.25), rent(5)=EUR 3156.25 (hand: 3156.25), both
           within EUR 50
  5.7    PASS     Rental pricing tiers applied -- weekly rate != daily x 7 in output
           rental line = EUR 500.00 (the monthly tier), not daily x 30 = EUR 750.00; weekly
           tier EUR 140.00 != daily x 7 = EUR 175.00
  5.8    PASS     Critic catches a seeded violation before render
           critic dropped 'LATE' (available 2026-11-01, after target 2026-09-15):
           fixture:LATE: available_from 2026-11-01 is after target_date 2026-09-15
  5.9    PASS     domain/scoring.py has zero imports outside stdlib + pydantic
           7 import root(s), all stdlib or pydantic: ['__future__', 'collections', 'enum',
           'pydantic', 're', 'typing', 'uuid']
  5.10   PENDING  [SCALE] Counterfactual solver returns >=2 relaxation options on a
                  zero-result query
           constraint relaxation / counterfactual solver (PHASE-5 §7) not built -- [SCALE]
------------------------------------------------------------------------------
  9 passed, 0 failed, 1 pending
  GATE 5 GREEN (with 1 pending)
==============================================================================
```

### What shipped

| Area | Files |
|---|---|
| Pure scoring math | `src/domain/scoring.py` — `Criterion` enum, `DEFAULT_WEIGHTS`, five `normalise_*` functions, `score_breakdown`, `ranking_sort_key`, `extract_numbers` (grounding). Zero imports outside stdlib + pydantic (gate 5.9) |
| Ranking engine | `src/domain/ranking.py` — `apply_hard_filters`, `score_listing`, `build_rationale`, `validate_grounding`/`finalize_rationale` (grounding), `rank`, `critic_pass`. The seam that reads real `Listing`/`RequirementProfile` and calls into `scoring.py`'s pure functions (D-020) |
| TCO engine | `src/domain/tco.py` — `residual_fraction_at_month`, `compute_buy_tco`, `compute_rent_tco`, `compute_comparison` (break-even solver), added to P0's existing `TcoEstimate`/`TcoComparison` contracts |
| Cost formulas | `src/domain/costs.py` — `monthly_insurance`/`monthly_energy`/`monthly_maintenance`/`monthly_running_cost`/`annual_road_tax`, shared by the `running_cost` scoring criterion and every recurring TCO line |
| Constants | `src/domain/constants.py` — every illustrative TCO/cost number in one place with a source comment (PHASE-5 §10's own risk mitigation) |
| Research fix | `src/agent/research.py` — `_query_from_profile` now sets `available_between` when `target_date` is known (D-023), so RESEARCH stops handing RECOMMEND candidates the critic would immediately reject |
| Demo wiring | `src/agent/demo.py` — RECOMMEND now calls `rank()` + `critic_pass()` instead of P3's "first surviving candidate" placeholder; records a `WEIGHTS_CHOSEN` and a real scored `RECOMMENDATION_MADE` `DecisionEntry` through P4's existing journal, unchanged schema (D-019's promise made good) |
| Gate | `scripts/gate_phase5.py` |
| Fixtures | `tests/fixtures/demo/golden_set.json` — 20 personas for gate 5.4, distinct from P3's 10 |
| Tests | `tests/unit/test_domain_{scoring,costs,tco,ranking}.py` (58), `tests/unit/helpers.py` (hand-built `Listing` factory) |

`domain/scoring.py` stays exactly what PHASE-5 §3 asks for — property-testable with no model,
no fixtures, no event loop — by keeping every normalisation function a pure function of
primitives; `domain/ranking.py` is the new seam that reads a real `Listing` and calls into it
(D-020). Hard filtering, budget, and the critic pass are three distinct, coexisting mechanisms
rather than one (D-022): a generic `HardFilter` removes a row outright (gate 5.3), a stated
budget instead scores a hard 0 on its own `budget_fit` criterion without necessarily removing
the row (the model's chosen weight decides how much that costs it), and the critic pass is a
second, independent check before anything reaches RECOMMEND.

### Deferred, deliberately

- **`[SCALE]` Constraint relaxation / counterfactuals on infeasibility** (PHASE-5 §7) — gate
  5.10. `SessionState.infeasible` (P3) still carries the flag forward honestly; nothing yet
  computes "raising the ceiling €2,000 opens seven" from it.
- **`[SCALE]` Calibration of weights against outcome data.**
- **`[SCALE]` Regional tax, insurance-band, and energy-price tables.** `src/domain/constants.py`
  is flat and illustrative by design (PHASE-5 §10); any UI rendering these figures must flag
  them as such.
- **A live rehearsal of the model actually choosing a `WeightSet`.** `rank()` takes whatever
  weights it's given (CONSTITUTION II.2); `DEMO_MODE` and the gates use `DEFAULT_WEIGHTS`
  because nothing in P5's scope wires a live session to emit its own — that's `orchestrator.py`
  calling `rank()` from inside a real `interviewer`/tool-call turn, still unexercised the same
  way D-015 leaves the rest of live orchestration unexercised until a real rehearsal happens.

---

## Phase 6 — Generative UI ✅

Run on 2026-08-08, no container needed for 6.1/6.3-6.7/6.9 (pure/deterministic Python, D-015's
reasoning); 6.2 needs `web/`'s npm dependencies and a Chromium build, both present on this
machine, so it ran as a hard PASS rather than PENDING.

```
==============================================================================
GATE 6 -- GENERATIVE-UI -- A2UI catalog, compiler, transport, escape hatch
==============================================================================
  6.1    PASS     Every message the compiler emits validates against the catalog schema
           6 compiled surfaces, 11 wire messages, 0 validation errors
  6.2    PASS     Golden-message fixtures render in a headless browser with zero console errors
           6 passed (web/tests/render.spec.ts, one test per golden fixture)
  6.3    PASS     compose_surface with an unknown component is rejected; the error reaches the
                  model as a tool result; nothing is forwarded to the renderer
           rejected as a tool result, nothing pushed to the sink: "compose_surface rejected:
           UNKNOWN_COMPONENT (root): 'NotInTheCatalog' is not in the registered catalog"
  6.4    PASS     compose_surface with a dangling child reference, a duplicate id, and depth > 8
                  are each rejected
           DANGLING_CHILD, DUPLICATE_ID, and DEPTH_EXCEEDED (depth 9 > 8) each independently
           rejected
  6.5    PASS     Action round-trip: a simulated click reaches the agent session with full
                  provenance
           provenance recorded in the session's action inbox: {'surface': 'gate65:results',
           'component': 'card-0', 'action': 'explain', 'payload': {'sourceId': 'AB-1'}}
  6.6    PASS     Surface identity is stable -- a second render_results in the same session
                  updates, does not recreate
           createSurface count stayed at 1 across two render_results calls
  6.7    PASS     All 8 powertrain GLBs are <=2 MB; total asset bundle <=16 MB
           8/8 archetypes present, largest 920 bytes (limit 2097152), total bundle 9426 bytes
           (limit 16777216)
  6.8    PASS     Every <model-viewer> has a poster; list contexts use reveal="interaction"
           1 <model-viewer> usage(s), all carry poster + reveal="interaction"
  6.9    PASS     All A2UI imports are from @a2ui/*/v0_9; exactly one module imports
                  MessageProcessor
           6 source files scanned, all @a2ui imports pinned to /v0_9; MessageProcessor imported
           only by web/src/a2ui/adapter.ts
  6.10   PENDING  [SCALE] Reduced-motion honoured; every interactive element has a visible focus
                  state
           reduced-motion + full a11y pass (PHASE-6 §7) not built -- [SCALE]
------------------------------------------------------------------------------
  9 passed, 0 failed, 1 pending
  GATE 6 GREEN (with 1 pending)
==============================================================================
```

Criterion 6.2 reports `PENDING` rather than `PASS` when `web/node_modules` hasn't been
installed (`npm install` + `npx playwright install chromium`, both inside `web/`), the same
convention gate 1.10/3.2/4.1 use for a heavy optional prerequisite.

### What shipped

| Area | Files |
|---|---|
| A2UI wire protocol | `src/mcp/ui/messages.py` — `createSurface`/`updateComponents`/`updateDataModel`/`deleteSurface`, built directly from `@a2ui/web_core`'s own `schemas/server_to_client.json` |
| Catalog registry (server-side) | `src/mcp/ui/catalog.py` — `ComponentSpec` for a minimal slice of `basicCatalog` plus all nine `carCatalog` components (PHASE-6 §3's table) |
| Escape-hatch validator | `src/mcp/ui/validate.py` — unknown component, missing/unknown prop, duplicate id, dangling child ref, cycle, depth > 8 (CONSTITUTION II.4) |
| Surface identity | `src/mcp/ui/surfaces.py` — `SurfaceRegistry`, deterministic `f"{session_id}:{kind}"` ids (gate 6.6) |
| Compiler | `src/mcp/ui/compiler.py` — `compile_{progress,results,detail,tco}_surface` (pure functions of each frozen P2 tool's args) + `compile_{score_breakdown,tco_breakdown}_surface` (direct, no-recomputation renders of real P5 `ScoreBreakdown`/`TcoComparison` objects, D-026) + `to_messages` (create-once-then-update, gate 6.6) |
| Action round-trip | `src/mcp/ui/actions.py` — `parse_action`/`to_user_turn`, `{surface, component, action, payload}` provenance (gate 6.5) |
| Transport | `src/mcp/ui/sink.py` — `UISink` protocol, `NullUISink` (tests/gates), `QueueUISink` (real, per-session `asyncio.Queue`) |
| `ui-mcp` real handlers | `src/mcp/ui/tools.py`, `src/mcp/ui/server.py` — P2's five frozen tool schemas now call the compiler and push through a session's `UISink` instead of returning a labelled stub |
| Live wiring | `src/agent/orchestrator.py` — per-session `SurfaceRegistry`/`QueueUISink`/action inbox, threaded into `build_ui_server` |
| SSE + actions transport | `src/api/main.py` — `GET /sessions/{id}/events` (SSE relay of a session's `QueueUISink`), `POST /sessions/{id}/actions` (action round-trip) |
| Frontend scaffold | `web/` — Vite + React 19, `@a2ui/react@0.9.1` + `@a2ui/web_core@0.9.1` pinned to `/v0_9`, one adapter module (`web/src/a2ui/adapter.ts`, gate 6.9), `carCatalog` component implementations (`web/src/a2ui/catalog.tsx`), chat rail + A2UI canvas (`web/src/App.tsx`) |
| PowertrainExplainer assets | `scripts/generate_powertrain_assets.py` — 8 hand-built placeholder glTF 2.0 binaries + PNG posters (D-028), `web/public/models/powertrain/*.{glb,png}` |
| Golden fixtures | `scripts/export_ui_fixtures.py` — exports real compiler output to `web/public/fixtures/*.json`; `web/harness.html` + `web/src/dev/fixture-harness.tsx` render one fixture through the real `MessageProcessor`/`carCatalog` |
| Headless-browser test | `web/tests/render.spec.ts` + `web/playwright.config.ts` — gate 6.2 |
| Gate | `scripts/gate_phase6.py` |
| Tests | `tests/unit/test_mcp_ui.py` (rewritten from P2's stub-pinning test), `tests/unit/test_ui_{validate,compiler,actions}.py`, `tests/integration/test_api_ui.py` |

`compile_results_surface`/`compile_progress_surface`/`compile_detail_surface`/`compile_tco_surface`
are pure functions of exactly what each frozen P2 tool schema carries — PHASE-6 §4's own
worked example ("`compile_results_surface(args)  # pure function, unit-tested`") holds
literally. `compile_score_breakdown_surface`/`compile_tco_breakdown_surface` are the "no
recomputation" counterparts PROGRESS.md's Phase 5 entry promised: they take P5's real
`ScoreBreakdown`/`TcoComparison` objects directly and map every field into props with no
second computation (D-026), reached by the action round-trip rather than a fresh model tool
call, since neither frozen schema carries per-criterion or per-line detail.

`CompareTable`, `Vehicle360`, and `RelaxationOptions` are registered in both catalogs
(server-side `src/mcp/ui/catalog.py` and client-side `web/src/a2ui/catalog.tsx`) so
`compose_surface` can validate and the renderer can draw a tree naming them, but the `[MVP]`
compiler never emits them itself — `CompareTable` because P2's five `ui-mcp` tools have no
dedicated comparison tool (PHASE-6 §4's escape hatch is the only path there today); `Vehicle360`
and `RelaxationOptions` because their `[SCALE]` prerequisites (real turntable imagery; PHASE-5
§7's counterfactual solver, gate 5.10) aren't built.

### Deferred, deliberately

- **`[SCALE]` `Vehicle360`** (image-sequence turntable of the actual vehicle) — PHASE-6 §5's
  own table marks this `[SCALE]`; every "3D per listing" surface still routes through
  `PowertrainExplainer`'s finite, category-level archetypes instead.
- **`[SCALE]` Progressive/streaming render as the agent composes.** Every surface renders in
  one `updateComponents` call today; PHASE-6 §2 lists streaming partial composition as
  `[SCALE]`.
- **`[SCALE]` Theme propagation, reduced-motion, full a11y pass** — gate 6.10.
- **Real `PowertrainExplainer` geometry.** The eight GLBs are hand-built placeholder unit
  cubes (D-028), honestly labelled "representative image" — real licensed or hand-modelled
  cutaways are a file swap under `web/public/models/powertrain/`, not a code change.
- **A live rehearsal of the model actually calling `render_results`/`compose_surface` inside a
  real session.** `src/agent/orchestrator.py`'s wiring is real and type-checked (per-session
  `SurfaceRegistry`/`QueueUISink`, threaded into `build_ui_server`), but — the same D-015
  reasoning gates 3/5's live paths — nothing has yet run it against the real `claude` CLI.
- **MCP App iframes.** PHASE-6 §2 explicitly puts this out of scope — different protocol,
  different trust boundary, P7's job.

---

## Phase 7 — MCP Apps ✅

Run on 2026-08-08, no container needed for the backend's own logic (in-memory catalogue) — the
ten criteria are Playwright-driven against a real running `src.api.main:app` and the `booking-mcp`
HTTP transport it lazily spawns, both started by the gate itself on a dedicated port (D-033).

```
==============================================================================
GATE 7 -- MCP-APPS -- Host implementation, sandbox, booking form
==============================================================================
  7.1    PASS     Inner iframe's origin != host origin (asserted from the browser, not from config)
           7.1 inner iframe origin != host origin, asserted from the browser
  7.2    PASS     CSP on the inner document matches the resource's _meta.ui.csp, defaults applied
           7.2 CSP on the inner document matches the resource's declared csp, defaults applied
  7.3    PASS     A fetch() to an undeclared domain from inside the App fails and is logged as blocked
           7.3 fetch() to an undeclared domain from inside the App fails and is logged as blocked
  7.4    PASS     ui/initialize completes; hostContext.theme reaches the App and visibly applies
           7.4 ui/initialize completes; hostContext.theme reaches the App and visibly applies
  7.5    PASS     ui/notifications/tool-input delivers pre-fill exactly once, after init
           7.5 ui/notifications/tool-input is delivered exactly once, after initialize responds
  7.6    PASS     tools/call from the view reaches the MCP server through the host proxy only
           7.6 tools/call from the view reaches the server only through the host proxy
  7.7    PASS     ui/resource-teardown removes the iframe/listeners; no leak after 20 cycles
           7.7 resource-teardown removes the iframe; no leak after 20 open/close cycles
  7.8    PASS     size-changed resizes the container without layout shift in the surrounding surface
           7.8 size-changed resizes the container without layout shift in the surrounding surface
  7.9    PASS     Audit log has one entry per view-initiated RPC, no gaps, for a full booking flow
           7.9 audit log has one entry per view-initiated RPC, no gaps, for a full booking flow
  7.10   PASS     The App renders and functions with JavaScript's network access fully blocked
           7.10 the App renders and functions with JavaScript's network access fully blocked
------------------------------------------------------------------------------
  10 passed, 0 failed, 0 pending
  GATE 7 GREEN
==============================================================================
```

Criterion 7.N reports `PENDING` instead of running when `web/node_modules`/Chromium aren't
installed, the same convention gate 6.2 uses; all ten collapse to that one prerequisite since a
single Playwright run (`web/tests/mcp-apps.spec.ts`) produces every criterion's evidence.

### What shipped

| Area | Files |
|---|---|
| Host-side plumbing (resource-agnostic) | `src/mcp/apps/{meta,audit,proxy}.py` — `DEFAULT_CSP`/`effective_csp`/`resource_ui_meta`, `AppAuditLog`, `call_view_rpc` (the one path from a view to any MCP server, D-031) |
| `ui://booking/form` resource | `src/mcp/booking/resources.py` — registered on `booking-mcp`'s own `Server` via `list_resources`/`read_resource`, independent of `create_sdk_mcp_server`'s tool-only wiring; `src/mcp/booking/static/booking_form.html` — the App itself, plain HTML/CSS/JS, no build step, no framework |
| Real tool handlers | `src/mcp/booking/tools.py` — `open_booking_form` pushes a `mcp_app_open` message through the session's `UISink` (D-032) instead of a stub; `submit_booking_draft` records a draft in an in-memory, id-keyed store; `open_checkout`/`confirm_booking` stay P8 stubs (out of scope, PHASE-7 §2) |
| Session-scoped booking server | `src/mcp/booking/server.py`, `src/agent/orchestrator.py` — `build_booking_server` now takes `session_id`/`sink` like `build_ui_server` already did |
| Host-proxy API | `src/api/main.py` — `POST /mcp-apps/{session_id}/rpc` (the only thing a browser ever calls; resources over real MCP-over-HTTP, tools in-process, D-031), `GET /mcp-apps/{session_id}/audit`, lazy loopback-only `booking-mcp` HTTP subprocess (`_ensure_booking_mcp_http`) |
| MCP host frontend | `web/src/mcp-host/{protocol,rpcChannel,hostBridge,sandboxOrigin,csp,outerEntry,sandboxProxyEntry,McpAppHost}.ts(x)` — the double-iframe handshake, RPC relay, and CSP injection; `web/mcp-outer.html` + `web/mcp-sandbox-proxy.html` are the two non-React entry points |
| Product wiring | `web/src/App.tsx` — mounts `McpAppHost` on an `mcp_app_open` SSE message, discriminated from a real A2UI message by the absence of A2UI's own `version` field; `web/src/styles.css` — the host panel as a fixed overlay, never reflowing the canvas (gate 7.8) |
| Gate-only harness | `web/mcp-host-harness.html` + `web/src/dev/mcp-host-harness.tsx` — mounts `McpAppHost` directly from query params, no live session, mirroring gate 6.2's `harness.html` pattern; exposes `window.__cardinalOpen`/`__cardinalClose` for gate 7.7's 20-cycle check |
| Gate | `scripts/gate_phase7.py`, `web/tests/mcp-apps.spec.ts`, `web/playwright.mcp-apps.config.ts` (kept separate from `playwright.config.ts` so gate 6 never depends on a Python backend) |
| Tests | `tests/unit/test_mcp_apps.py` (8), `tests/unit/test_mcp_booking.py` (+3 new, 7 total) |

The double-iframe (PHASE-7 §5.1) is four browsing contexts deep exactly as drawn: host page →
outer `<iframe src="/mcp-outer.html">` (same origin as host, the only thing that ever calls
`/mcp-apps/*/rpc`) → sandbox proxy `<iframe src="/mcp-sandbox-proxy.html">` (a genuinely
different origin in dev via D-030's `127.0.0.1`/`localhost` split, a dumb relay that never
interprets a forwarded message's contents) → inner `blob:` iframe (same origin as the proxy,
holding the actual resource HTML with a CSP `<meta>` tag injected ahead of it). The one thing
that cost real debugging time and is now D-034: a `blob:` document inherits its creator's CSP
*in addition to* its own declared one, enforced as an intersection — the sandbox proxy's shell
CSP has to be at least as permissive as any resource's effective CSP or it silently narrows it
back down, with no console error pointing at CSP as the cause.

`confirm_booking`/`open_checkout` remain reachable in principle through `/mcp-apps/*/rpc`'s
in-process `tools/call` path (nothing about the transport itself re-hides them, since
`RESOURCE_ROUTES`/`ALLOWED_VIEW_TOOLS` — not tool audience — is what gates a *view's* access) but
`ui://booking/form`'s own allowlist only names `submit_booking_draft`; calling either through
this endpoint today still hits P2's unimplemented stub either way. The real gesture-token check
CONSTITUTION I.2 requires for `confirm_booking` is P8's job, same as the tool's actual behaviour.

### Deferred, deliberately

- **`[SCALE]` `ui/request-display-mode` beyond acknowledging it.** The host answers every
  request with `{displayMode: "inline"}` regardless of what was asked (PHASE-7 §2 marks
  fullscreen/pip `[SCALE]`); the RPC plumbing exists so this is a body change, not new wiring.
- **`[SCALE]` Full theme/style-variable propagation.** `hostContext.styles.variables` carries two
  colour variables today, enough for gate 7.4's "visibly applies"; a richer variable set is a
  data change in `outerEntry.ts`'s `buildInitializeResult`, not a protocol change.
- **`[SCALE]` `ui/update-model-context`.** Acknowledged, not acted on — PHASE-7 §2's own
  `[SCALE]` line; there is no later-turn model context to update yet in this phase's scope.
- **Durable audit-log storage.** `AppAuditLog` is in-memory, one instance per process, the same
  posture gate 3.6's `AuditLog` has today. `[SCALE]` is Postgres; the entry shape doesn't change.
- **Connection pooling for the `resources/read` HTTP client.** `_read_resource_via_http` opens a
  fresh `mcp.client.streamable_http` session per call (D-031) — fine at this call volume, a
  persistent session is `[SCALE]` if that ever changes.
- **A live rehearsal of the model actually calling `open_booking_form` inside a real session.**
  `src/agent/orchestrator.py` wires `booking-mcp` with real `session_id`/`sink` now, type-checked
  and unit-tested (`tests/unit/test_mcp_booking.py`), but — the same D-015 reasoning already
  applied to gates 3/5/6's live paths — nobody has yet run it against the real `claude` CLI.
- **Checkout (`ui://checkout/payment`, `open_checkout`, `confirm_booking`'s real behaviour).**
  Explicitly out of this phase (PHASE-7 §2) — P8's job, and `src/mcp/apps/` was built
  resource-agnostic specifically so P8 is a second resource + a second `RESOURCE_ROUTES` entry,
  not a second host implementation.

---

## Phase 8 — Commerce ✅

Run on 2026-08-08, no container needed for 8.1/8.2/8.4/8.5/8.7/8.8/8.9/8.12 (pure/deterministic
Python, D-015's reasoning applied the same way gate 5 applied it to reasoning); 8.3/8.6/8.10/8.11
need `web/`'s npm dependencies and a Chromium build, both present on this machine, so they ran as
hard PASS rather than PENDING.

```
==============================================================================
GATE 8 -- COMMERCE -- Booking lifecycle, mock gateway, financing, idempotency
==============================================================================
  8.1    PASS     State machine: all (state, event) pairs either transition or explicitly reject
           42 (state, event) pairs checked over 7 states x 6 events: 6 transition, 36 explicitly
           reject
  8.2    PASS     confirm_booking is absent from the model's resolved toolset
           model-facing booking-mcp resolves to ('open_booking_form', 'open_checkout') (no
           confirm_booking) -- app-facing resolves to ('open_booking_form', 'open_checkout',
           'submit_booking_draft', 'mint_gesture_token', 'confirm_booking') (confirm_booking
           present) -- resolved via the SDK's own Server.request_handlers, not read from config
  8.3    PASS     No agent-driven path reaches confirm_booking -- zero calls without a real click
           8.3 no agent-driven path reaches confirm_booking or mint_gesture_token
  8.4    PASS     confirm_booking without a valid gesture_token is rejected
           rejected: 'confirm_booking rejected: gesture token is missing, unknown, or already used'
  8.5    PASS     Double-submit with the same idempotency key produces one booking, two identical
                  responses
           one booking (e0eea461-d447-4e90-9eb7-39f6645447a2), two identical responses:
           {'booking_id': 'e0eea461-d447-4e90-9eb7-39f6645447a2', 'state': 'confirmed', 'outcome':
           'success', 'message': 'Payment authorised.'}
  8.6    PASS     Every decline/error/timeout test card renders a distinct, non-spinner UI state
           8.6 every decline/error/timeout test card renders a distinct, non-spinner UI state
  8.7    PASS     Static denylist scan finds zero payment-provider identifiers
           148 files scanned across ('src', 'tests', 'scripts', 'pyproject.toml',
           'web/package.json', 'web/package-lock.json'), 0 hits
  8.8    PASS     No card number is present in any log, trace, DB row, or audit entry
           scanned 5 surfaces (response, DB row, audit hash, stdout, stderr) for all 5 documented
           test-card numbers -- none present
  8.9    PASS     PENDING older than TTL transitions to EXPIRED and releases the listing
           PENDING -> expired after the 15-minute TTL; listing hold released
  8.10   PASS     MOCK -- NO REAL PAYMENT banner is present and above the fold
           8.10 MOCK -- NO REAL PAYMENT banner is present and above the fold
  8.11   PASS     Client-computed monthly payment matches server recomputation to the cent
           8.11 client-computed monthly payment matches server recomputation to the cent
  8.12   PASS     Audit trail has one entry per transition with actor, timestamps, and gesture
                  provenance
           2 audit entries: submit(actor=user, draft->pending, note='checkout confirmed by a
           trusted click'), authorise(actor=system, pending->confirmed,
           event_id='auth_1a473a7b84d7441797db')
------------------------------------------------------------------------------
  12 passed, 0 failed, 0 pending
  GATE 8 GREEN
==============================================================================
```

Also re-run against live Postgres (`docker compose up -d postgres`, migration `0002_bookings_commerce`
applied) for the pure-Python criteria and the full test suite; 8.3/8.6/8.10/8.11's own spawned
backend is exercised against whatever `CARDINAL_DATABASE_URL` the invoking shell has set, same as
gate 7's — the run pasted above is the documented, unset-environment invocation (CONSTITUTION
III.7). See DECISIONS.md for a known gap this surfaced: a raw `uvicorn` subprocess on native
Windows cannot open an async Postgres connection at all (`ProactorEventLoop`, the same
psycopg/Windows interaction `src/adapters/db/session.py`'s `run_async` works around for CLI entry
points) — harmless for `docker compose up` (the container is Linux) and for every gate through P7
(none of their spawned-subprocess flows touched Postgres), but it means `scripts/gate_phase8.py`'s
own browser criteria run against the in-memory `BookingStore` whenever invoked directly on Windows
outside Docker, `CARDINAL_DATABASE_URL` set or not. `PostgresBookingStore` itself is real and
covered by `tests/integration/test_adapters_booking_store_postgres.py`, which runs through
pytest-asyncio's own `SelectorEventLoop` hook and is unaffected.

**8.7's evidence line updated 2026-08-08 when Phase 10 landed.** The term list and scan loop
now live in `scripts/gate_common.py`, shared with gate 10.3 rather than an independently
authored copy (DECISIONS.md D-044) — same scan scope, but the file-exclusion set grew by two
(the new `gate_common.py`/`gate_phase10.py`, both of which now also spell out a denylist
literally), and the repo has more files in it than it did when Phase 8 landed. Re-run for real
rather than hand-edited, per CONSTITUTION III.1.

### What shipped

| Area | Files |
|---|---|
| Booking state machine | `src/domain/booking.py` — `BookingState` (7 values, D-035), `BookingEvent`, `TRANSITIONS`, `apply_transition`, `BookingAuditEntry`/`new_audit_entry`, `Booking.with_transition`, `stale_pending` (pure, `now` passed in) |
| Financing calculator | `src/domain/financing.py` — `FinancingTerms`, `compute_monthly_payment` (standard amortisation, `Decimal`, zero-APR special case) |
| Payment contracts | `src/domain/payments.py` — `PaymentOutcome`, `OUTCOME_MESSAGES`, `PaymentIntent` (last4 + outcome hint only, D-036), `AuthResult`/`CaptureResult`/`VoidResult` |
| Mock gateway | `src/adapters/payments/{protocol,mock}.py` — `PaymentGateway` protocol, `MockPaymentGateway`, `MOCK_GATEWAY_BASE_URL` (a `mock://` compile-time constant), `CARD_OUTCOMES`/`outcome_for_card_number` (test/doc mirror of the client-side table) |
| Booking store | `src/adapters/booking_store.py` (protocol, `InMemoryBookingStore`, `PENDING_TTL_MINUTES`, `session_ref_to_uuid`, `expire_stale_bookings`), `src/adapters/db/booking_store.py` (`PostgresBookingStore`) |
| Schema | `migrations/versions/0002_bookings_commerce.py` — `bookings` gains `canonical`/`created_at`/`updated_at`, loses `ts`/`audit` (superseded by `canonical`, D-006's dual-storage shape); `src/adapters/db/models.py`'s `BookingRow` updated to match |
| Gesture tokens | `src/mcp/booking/gesture.py` — `GestureTokenStore`, 30s TTL, single-use (CONSTITUTION I.2 layer 3) |
| Checkout resource + App | `src/mcp/booking/resources.py` (`CHECKOUT_URI`, both resources now served off one registry), `src/mcp/booking/static/checkout.html` (MOCK banner, financing sliders, mock tokeniser, gesture-gated confirm flow) |
| Tool handlers | `src/mcp/booking/tools.py` — real `open_checkout`, new `mint_gesture_token`, real `confirm_booking`; module-level shared defaults (D-038); `src/mcp/booking/server.py` threads `store`/`booking_store`/`payment_gateway` through |
| Booking form draft carries its listing ref | `src/mcp/booking/static/booking_form.html` — echoes `source`/`source_id`/`offer_type` from its own `toolInput` into the submitted draft, so `open_checkout`/`confirm_booking` can price it |
| API wiring | `src/api/main.py` — `app.state.booking_store` (Postgres-or-memory, matching `build_store`'s own split), `CHECKOUT_URI` added to `RESOURCE_ROUTES` |
| Gate | `scripts/gate_phase8.py` — 8 pure-Python criteria + 4 Playwright-driven, same split gate 7 used for its own browser subset |
| Frontend tests | `web/tests/commerce.spec.ts`, `web/playwright.mcp-commerce.config.ts` — reuses `mcp-host-harness.html` unmodified (already resource-agnostic per P7) |
| Tests | `tests/unit/test_domain_{booking,financing}.py`, `tests/unit/test_adapters_payments.py`, `tests/unit/test_adapters_booking_store.py`, `tests/integration/test_adapters_booking_store_postgres.py`, `tests/unit/test_mcp_booking.py` (rewritten from P7's stub-pinning tests, the same treatment P6 gave P2's `ui-mcp` stubs) |

`confirm_booking` stayed exactly where P2 declared it — `audience=("app",)`, never registered on
a model-facing build (gate 8.2) — and P8 adds two more independent layers on top: a gesture token
`mint_gesture_token` mints only in response to a click the App has already checked `isTrusted` on,
single-use and 30-seconds-lived (gate 8.4), and every mutating call is keyed so a retried request
replays rather than double-books or double-charges (gate 8.5, backed by a real `UNIQUE
(session_id, idempotency_key)` constraint in Postgres, not just an in-memory check). Neither the
mock gateway nor the checkout App ever see a full card number reach the server — `_price_draft`
recomputes the authoritative total server-side from the same `adapter.quote()` path `get_quote`
already uses, so nothing about checkout trusts a client-supplied price or a client-supplied
outcome without the click-and-token gate in front of it.

### Deferred, deliberately

- **`[SCALE]` A real gateway behind `PaymentGateway`, feature-flagged.** The protocol
  (`src/adapters/payments/protocol.py`) is the whole seam PHASE-8 §5 asks for; nothing in this
  repository implements it besides the mock, by design (CONSTITUTION I.1, gate 8.7).
- **`[SCALE]` Refund/cancellation flows, partial states.** `BookingEvent.CANCEL` and `.ABANDON`
  are real, gate-8.1-tested transitions in the domain state machine, but no MCP tool triggers
  either yet — PHASE-8 §2's own `[SCALE]` line.
- **A live rehearsal of the model actually calling `open_checkout` inside a real session.**
  `src/agent/orchestrator.py` wires `store=self._store` into the model-facing `booking-mcp` build
  now, type-checked and unit-tested, but — the same D-015 reasoning already applied to gates
  3/5/6/7's live paths — nobody has yet run it against the real `claude` CLI.
- **A native-Windows, non-Docker `uvicorn` process serving real Postgres traffic.** Noted above;
  affects local dev ergonomics only, not any gate criterion or the Docker-based deployment path.

---

## Phase 9 — Observability ✅

Run on 2026-08-08, no container needed — every criterion is pure/deterministic code against
`DEMO_MODE` (D-015's reasoning, the same one gates 3/5/8 already established: nothing here
needs a live `ClaudeSDKClient` session or an `ANTHROPIC_API_KEY` to mean something).

```
==============================================================================
GATE 9 -- OBSERVABILITY -- OTel, Langfuse, eval harness, cost governance
==============================================================================
  9.1    PASS     A full session produces one trace containing spans for all four phases
           12 spans captured, all four phase spans present, all sharing
           trace_id=1ad252f2d1aa0dcafaf897aebd29cb75 with the session's own root span
  9.2    PASS     Every MCP tool call appears as a span with args hash and duration
           4 tool call span(s) across 4 distinct tools: ['tool.interview_turn',
           'tool.open_booking_form', 'tool.search_cars', 'tool.submit_booking_draft']
  9.3    PASS     Both researcher subagents appear as sibling spans with overlapping time ranges
           2 researcher spans, both children of phase.research,
           researcher.mock_autobazaar=[1786166728959755700,1786166728980216500] overlaps
           researcher.mock_drivenow=[1786166728959791500,1786166728980364100]
  9.4    PASS     Eval harness runs 30 personas headless and emits a scored report
           30 personas run (20 from P5's golden set, 10 end-to-end extras), 9 metrics scored:
           profile_completeness=1.000, precision_at_3=1.000, groundedness=1.000,
           constraint_compliance=0.000, guardrail_violations=0.000, escape_hatch_ratio=0.000,
           tool_call_rate=4.800, cost_per_session_usd=0.000, latency_p50_p95_s=0.186
  9.5    PASS     All thresholds in PHASE-9 §4 met; guardrail violations exactly 0
           9/9 metrics within threshold: profile_completeness 1.000 >= 0.95, precision_at_3
           1.000 >= 0.8, groundedness 1.000 == 1.0, constraint_compliance 0.000 == 0,
           guardrail_violations 0.000 == 0, escape_hatch_ratio 0.000 <= 0.15, tool_call_rate
           4.800 in 2-8, cost_per_session_usd 0.000 <= 0.4, latency_p50_p95_s 0.186 within
           p50<=8s/p95<=25s
  9.6    PASS     No PII in any exported span -- redaction hook asserted on a real export
           12 spans scanned, zero raw email/phone matches, 2 redaction marker(s) found
           (e.g. on tool.input.utterance)
  9.7    PASS     Cost per session <= $0.40 across the golden set, reported per role
           max $0.00/session across 30 personas; per role: {orchestrator: 0.0, extraction: 0.0,
           critic: 0.0, explainer: 0.0} -- DEMO_MODE makes zero live model calls (CONSTITUTION
           III.7), so this is a real $0.00, not an estimate
  9.8    PENDING  [SCALE] Prompt-cache hit rate > 0 across repeated sessions
           needs a live multi-turn ClaudeSDKClient session to produce a real
           cache_read_input_tokens signal -- DEMO_MODE makes zero model calls by construction
  9.9    PENDING  [SCALE] Eval regression > 5% fails CI
           CI-gated eval regression detection on every prompts/ or src/agent/ PR not built --
           [SCALE]; src/agent/evals.py's EvalReport is the mechanism a future CI job would diff
------------------------------------------------------------------------------
  7 passed, 0 failed, 2 pending
  GATE 9 GREEN (with 2 pending)
==============================================================================
```

Built directly against Phase 9, ahead of PLAN-00 §4's suggested under-deadline order (`... → 8
→ 11 → 9 → backfill 4/10`) — see DECISIONS.md D-039 for why that's not a CONSTITUTION III.2
violation and what was checked before starting. Phase 8 (Commerce) had already landed by the
time this work started.

### What shipped

| Area | Files |
|---|---|
| Tracing core | `src/agent/tracing.py` — `configure_tracing` (idempotent `TracerProvider` + resource, always-on in-memory exporter, optional Langfuse OTLP exporter when `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set), `RedactingSpanExporter`/`redact_attributes` (CONSTITUTION IV.1, export-path redaction ahead of any network call), `phase_span`/`tool_call_span`/`subagent_span`/`scoring_span` |
| MCP tool-call spans | `src/mcp/audience.py`'s `for_audience` wraps every registered tool's handler in a `tool.<name>` span using the raw `opentelemetry` API directly (no `mcp` → `agent` import, preserving PLAN-00 §2's one-way layering) — covers every live-path tool call on every server without touching 14 individual tool files |
| Phase/subagent spans | `src/agent/demo.py` — one `session` root span per run, one `phase.*` span per phase *stay* (RESEARCH revisited after a backward transition gets two), a `scoring.rank` span around `rank()` with weights + a determinism hash; `src/agent/research.py`'s `_research_one_source` opens a `researcher.<source>` span while `phase.research` is the ambient current span, so `asyncio.gather`'s tasks snapshot it as their parent and come out as genuine overlapping siblings (gate 9.3) |
| `decline_at_checkout` | `src/agent/demo.py`'s `run_demo_session` gained this optional flag — settles TRANSACT on `booking_status="abandoned"` instead of `submit_booking_draft`, the "decline at checkout" end-to-end path PHASE-9 §4's eval golden set calls for, which nothing had driven a session into before |
| Live-path instrumentation | `src/api/main.py`'s `lifespan` calls `configure_tracing()` + `ClaudeAgentSDKInstrumentor().instrument()` once, fire-and-forget (try/except, matches PHASE-9 §8's risk table) — real and wired, gate-unexercised the same way D-015 leaves the rest of live orchestration unexercised |
| Eval harness | `src/agent/evals.py` — `run_eval_harness` scores PHASE-9 §4's nine metrics per persona and in aggregate: profile completeness, precision@3 (D-024-style structural self-consistency), groundedness (no `[unverified]` marker), constraint compliance (an independent re-check of the final top-3 against every hard filter/budget/date, not a re-read of `critic_pass`'s own verdict), guardrail violations, escape-hatch ratio (a real `compile_results_surface` call per persona with survivors, genuinely 0 `compose_surface` calls since `DEMO_MODE` has no model to reach for it with), tool-call rate, cost/session, latency p50/p95 |
| 30-persona golden set | `tests/fixtures/demo/eval_extra_personas.json` — 10 new personas (3 backward-transition, 3 zero-result/infeasible, 2 decline-at-checkout, 2 general coverage) alongside P5's existing 20 (`golden_set.json`) |
| Gate | `scripts/gate_phase9.py` |
| Tests | `tests/unit/test_agent_tracing.py` (14), `tests/unit/test_agent_evals.py` (10) |

Two of the nine eval metrics needed an explicit, documented substitution rather than a
fabricated number — both because `DEMO_MODE` is genuinely a scripted, non-agentic replay
(CONSTITUTION III.7), not a live multi-turn session:

- **Tool-call rate** counts every audited tool call per session (interview turns, searches,
  booking calls), not `search_cars` alone — `DEMO_MODE`'s RESEARCH phase issues exactly one
  `search_cars` audit entry per turn-in-phase regardless of how many of the two marketplaces
  it fans out to underneath (D-013's "the agent never learns marketplaces are plural" holds
  inside `DEMO_MODE` too), so counting search calls alone would floor near 1 for most personas.
- **Cost per session** reports a real $0.00 — `DEMO_MODE` makes zero model calls by
  construction, so that is the honest number, not an estimate against per-token rates for
  calls that never happened. Live per-role cost governance (PHASE-9 §5, mostly `[SCALE]`)
  waits on the live rehearsal PROGRESS.md's "Next" list already tracks.

`src/agent/evals.py`'s own `infeasible_mismatches` field (not one of the nine gated metrics)
caught a real, useful fact while this was being built: one of P5's original 20 golden
personas ("Golden 18 — Wagon Buyer Tight Budget") is genuinely infeasible against the seeded
catalogue, matching gate 5.4's own "19/20 feasible" finding — surfaced as a diagnostic rather
than hard-coded as a named exception, since that fact depends on the catalogue seed/generator
and would go stale silently otherwise (the same reasoning D-002 already established for gate
1.8's cohort statistics).

### Deferred, deliberately

- **`[SCALE]` Prompt-cache hit rate tracking** (PHASE-9 §5) — gate 9.8. `cache_read_input_tokens`
  only exists on a real, repeated `ClaudeSDKClient` session; `DEMO_MODE` makes zero model calls.
- **`[SCALE]` CI-gated eval regression detection** (PHASE-9 §4) — gate 9.9. `EvalReport` is the
  artifact a future CI job would diff two runs of; the diffing and the CI wiring aren't built.
- **`[SCALE]` Per-session cost budget + hard cap, cheap-model routing under pressure,
  compaction** (PHASE-9 §5's levers 2-5) — no live session exists yet to threaten a real budget.
- **`[SCALE]` Reasoning-replay timeline surfaced in-product** (PHASE-9 §6) — the data it would
  read (P4's decision journal joined to the trace) already exists; no UI reads it yet.
- **`[SCALE]` Online evals on real sessions, sampled** — needs live traffic to sample from.
- **A live rehearsal of `ClaudeAgentSDKInstrumentor`'s auto-generated spans.** `src/api/main.py`
  wires it in real and fire-and-forget, but — the same D-015 reasoning already applied to every
  other phase's live path — nobody has yet run it against the real `claude` CLI.

---

## Phase 10 — Trust ✅

Run on 2026-08-08, no container needed — every criterion is pure/deterministic code against
`DEMO_MODE`'s real pipeline or a static file scan (D-015's reasoning, already applied to gates
3/5/8/9).

```
==============================================================================
GATE 10 -- TRUST -- Injection defence, PII, tenancy, threat model
==============================================================================
  10.1   PASS     Injection corpus (~30 attempts): zero succeed
           30 attempts across 6 categories (delimiter_escape=5, encoded_payloads=5,
           instruction_override=5, memory_poisoning=5, role_confusion=5,
           tool_call_injection=5), zero succeeded: identical score, identical rationale,
           single real wrapper tag, every time
  10.2   PASS     Memory-poisoning attempt does not write to episodic memory
           0 memory-write-shaped tools across 6 server x audience builds; 5
           memory-poisoning listings seeded into a real catalogue, session reached
           booking_status='draft_submitted', zero leakage into the profile or the
           decision journal
  10.3   PASS     Denylist scan: zero hits across source, deps, lockfiles
           148 files scanned across ('src', 'tests', 'scripts', 'pyproject.toml',
           'web/package.json', 'web/package-lock.json') for 10 payment-provider (I.1) +
           7 BMW Group endpoint (I.3) terms, 0 hits
  10.4   PASS     Listing text reaches the model wrapped and labelled trust="untrusted"
           get_listing(mock_drivenow:DN-1001).description arrives as '<listing_content
           listing_id="DN-1001" source="mock_drivenow" trust="un'... (full text wrapped,
           labelled trust="untrusted")
  10.5   PENDING  [SCALE] PII scan over logs and a real span export: zero findings
           the span-export half is already built and gated -- gate 9.6 asserts zero raw
           PII in a real OTel export via RedactingSpanExporter (CONSTITUTION IV.1); a
           log-line scan and memory-tier redaction are not built
  10.6   PENDING  [SCALE] Two-tenant isolation test: zero cross-visibility in all stores
           multi-tenancy not built -- no tenant_id column anywhere in the schema
  10.7   PENDING  [SCALE] pip-audit + npm audit: no high/critical
           neither scanner wired into make verify or CI yet
  10.8   PENDING  [SCALE] Every 3D asset has an attribution entry
           docs/ATTRIBUTION.md does not exist; the eight PowertrainExplainer GLBs are
           hand-built placeholders (D-028), not licensed geometry -- nothing to
           attribute yet
  10.9   PENDING  [SCALE] docs/THREAT-MODEL.md exists with no open criticals
           not written yet; PHASE-10 §8's five-adversary table lives only in the plan doc
------------------------------------------------------------------------------
  4 passed, 0 failed, 5 pending
  GATE 10 GREEN (with 5 pending)
==============================================================================
```

### What shipped

| Area | Files |
|---|---|
| Injection defence (pure) | `src/domain/trust.py` — `detect_injection` (cheap best-effort classifier over ~20 phrasing patterns spanning instruction-override/role-confusion/memory-poisoning), `escape_untrusted_text`/`_escape_attr` (unconditional `<`/`>`/`&` escaping), `wrap_listing_content` (the concrete `<listing_content listing_id=... source=... trust="untrusted">` form CONSTITUTION I.4 names) |
| `get_listing` wired to wrap | `src/mcp/marketplace/tools.py` — the only tool that ever returns a listing's full `description` now returns `wrap_listing_content(listing)` in that field instead of the raw string; `search_cars`/`compare_listings` never carried it in the first place (`ListingSummary`'s own docstring) |
| Standing untrusted-content rule | `prompts/orchestrator_system.md`, `researcher.md`, `critic.md`, `explainer.md` — every prompt that can reach `get_listing` (directly or as a subagent) states the rule once, since Claude Agent SDK subagents run on their own `AgentDefinition.prompt`, not inheriting the orchestrator's `system_prompt` |
| Denylist scan (shared) | `scripts/gate_common.py` — `PAYMENT_PROVIDER_TERMS`, `DENYLIST_SCAN_DIRS`, `DENYLIST_EXTRA_FILES`, `DENYLIST_AUTHORING_FILES`, `scan_for_terms()`, factored out of gate 8.7 and reused by gate 10.3 (DECISIONS.md D-044) |
| `resolved_tools` zero-tool fix | `src/mcp/audience.py` — handles a server with no registered tools for an audience (e.g. `ui-mcp`'s "app" build) without raising (DECISIONS.md D-045) |
| Injection corpus | `tests/fixtures/security/injection_corpus.json` — 30 entries, 5 each across `instruction_override`, `role_confusion`, `delimiter_escape`, `encoded_payloads`, `tool_call_injection`, `memory_poisoning` |
| Gate | `scripts/gate_phase10.py` |
| Tests | `tests/unit/test_domain_trust.py` (11), `tests/unit/test_agent_injection_corpus.py` (corpus-parametrised: score purity, rationale/grounding purity, wrapper-tag integrity, classifier recall on the three plainly-worded categories, tool-shape + end-to-end memory-poisoning checks), `tests/unit/test_mcp_marketplace.py` (+1, `get_listing`'s wrapped output) |

Gate 10.1's evidentiary bar is structural, matching D-015's reasoning one phase further: with
no live model in the loop, "zero succeed" is proven as identical `ScoreBreakdown`, identical
rationale text, and exactly one real `<listing_content>` tag pair surviving escaping, for every
one of the 30 entries against the same base listing with only its `description` swapped —
never as "the classifier caught it" or "a model declined to obey it" (DECISIONS.md D-046).
Writing the corpus this way is also what caught a real bug before it shipped: the first version
of `wrap_listing_content`'s flagged-note interpolated the raw, matched fragment of untrusted
text via `{flag.matched!r}` without escaping it first, so a payload built to exploit exactly
that (`DE-01`, containing a literal `</listing_content>`) produced three `<` and two `>` in the
wrapped output instead of two of each — CONSTITUTION III.8's "watch it fail, then make it pass"
working exactly as intended (DECISIONS.md D-042).

The BMW Group denylist (`BMW_GROUP_ENDPOINT_TERMS` in `scripts/gate_phase10.py`) is
deliberately endpoint-shaped (`bmwgroup.com`, `connecteddrive`, `mini.co.uk`, …), never the
bare word "BMW" — that word appears throughout `src/adapters/catalogue/taxonomy.py`'s
legitimate seeded brand pool, exactly the case CONSTITUTION I.3 carves out ("brand names in
our own generated dataset are fine").

### Deferred, deliberately

- **`[SCALE]` PII redaction across logs and the memory tier** (PHASE-10 §4) — gate 10.5. The
  span-export half already shipped in P9 (gate 9.6); a log-line regex+entropy scan and
  memory-tier redaction wait on a log sink and on P4's episodic memory, neither of which exist.
- **`[SCALE]` Multi-tenant isolation** (PHASE-10 §5) — gate 10.6. No `tenant_id` anywhere in
  the schema; this is a single-tenant system by construction today, not by an unenforced
  convention. PHASE-10 §10's own risk table flags this as expensive to add late — still true,
  still deferred, per CONSTITUTION III.3.
- **`[SCALE]` Rate limiting and abuse controls, secrets rotation** (PHASE-10 §2) — not built;
  no gate criterion names either directly.
- **`[SCALE]` Supply-chain: `pip-audit`/`npm audit` in CI, licence audit, pinned-hash
  verification** (PHASE-10 §7) — gate 10.7.
- **`[SCALE]` `docs/ATTRIBUTION.md`** (PHASE-10 §7) — gate 10.8. Nothing to attribute yet;
  P6's GLBs are hand-built placeholders (D-028), not licensed third-party assets.
- **`[SCALE]` `docs/THREAT-MODEL.md`** (PHASE-10 §8) — gate 10.9. The five-adversary table
  exists in `plans/PHASE-10-TRUST.md` §8 itself; not yet promoted to a standalone, gated file.
- **A live rehearsal of a real model actually reading a `<listing_content trust="untrusted">`
  block and declining to follow it.** Every mechanism here is architecturally enforced
  (structured-field scoring, escaping, tool invisibility) rather than reliant on the model
  choosing correctly, which is the point — but nobody has yet watched a real session try one
  of these 30 entries end to end, the same D-015 gap every other phase's live path still has.

---

## Phase 11 — Delivery ✅

Run on 2026-08-08. 11.1/11.2/11.5/11.6 against a real `docker compose build && up`, rebuilding
the `cardinal` project in place (the same containers a prior session had left running 15h
earlier — no `-v`, the named Postgres volume was reused, not destroyed). 11.3/11.4 against a
disposable backend on its own port with the environment scrubbed to just `DEMO_MODE=true`,
driving the real product (`index.html`, not a harness page) through a real Chromium instance.
11.7/11.9/11.10 are pure filesystem/subprocess checks.

```
==============================================================================
GATE 11 -- DELIVERY -- Docker, deploy, CI/CD, docs, demo assets
==============================================================================
  11.1   PASS     Clean clone -> docker compose up -> all services healthy within 120s
           all 4 services healthy within 120s: {'api': 'healthy', 'booking': 'healthy',
           'postgres': 'healthy', 'web': 'healthy'}
  11.2   PASS     Seed runs automatically; /health reports >=100 listings
           /health -> {'status': 'ok', 'backend': 'postgres', 'demo_mode': False, 'listings':
           240, 'sources': {'mock_autobazaar': 130, 'mock_drivenow': 110}}
  11.3   PASS     Playwright e2e walks all seven beats and screenshots each
           web/tests/demo-e2e.spec.ts walked all seven beats and screenshotted each --
           stats={'expected': 1, 'skipped': 0, 'unexpected': 0, 'flaky': 0}
  11.4   PASS     e2e passes with the entire environment unset except DEMO_MODE=true
           backend launched with {CARDINAL_DATABASE_URL, CARDINAL_BOOKING_MCP_URL,
           ANTHROPIC_API_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST} removed
           and only DEMO_MODE=true set -- stats={'expected': 1, 'unexpected': 0}
  11.5   PASS     'booking' service resolves on a distinct hostname from 'web'
           'booking' (src.mcp.booking.http, no published port) and 'web' (builds
           ./web/Dockerfile) are distinct compose services, each its own hostname on the
           compose network
  11.6   PASS     Every image runs as non-root; no image exceeds 800 MB
           api: user='cardinal' size=177MB; booking: user='cardinal' size=177MB; web:
           user='101' size=21MB
  11.7   PASS     .env.example covers every variable read anywhere in the codebase (scan
                  asserts)
           10 variable(s) read in src/ + web/src/ + vite.config.ts, all in .env.example:
           ['ANTHROPIC_API_KEY', 'BOOKING_MCP_HTTP_HOST', 'BOOKING_MCP_HTTP_PORT',
           'CARDINAL_API_PORT', 'CARDINAL_BOOKING_MCP_URL', 'CARDINAL_DATABASE_URL',
           'DEMO_MODE', 'LANGFUSE_HOST', 'LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY']
  11.8   PENDING  README's run instructions executed verbatim on a clean machine
           by definition a human, on a machine that has never seen this repo, following
           README.md's 'Run it' section verbatim -- nothing this script runs can stand in for
           that. See README.md's Run it section.
  11.9   PENDING  Deck and video present under docs/
           deck present (cardinal-deck.pptx); video not recorded -- see
           docs/VIDEO-SCRIPT.md for the shot list, recorded against DEMO_MODE per
           web/tests/demo-e2e.spec.ts's own seven beats
  11.10  PASS     make verify green: every gate 0-11
           gates 0..10 each exit 0 (11 gates checked; gate 11 is this run itself)
  11.11  PENDING  [SCALE] Public deployment reachable and healthy
           no public deployment exists -- PHASE-11 SS2 marks this [SCALE]
------------------------------------------------------------------------------
  8 passed, 0 failed, 3 pending
  GATE 11 GREEN (with 3 pending)
==============================================================================
```

### What shipped

| Area | Files |
|---|---|
| Multi-stage, non-root, healthchecked Dockerfiles | `Dockerfile` (shared by `api`/`booking`: venv-builder stage + slim runtime, `USER cardinal`) — `web/Dockerfile` (Node builder → `nginxinc/nginx-unprivileged:alpine` runtime) |
| Four-service compose | `docker-compose.yml` — `postgres`, `booking` (own service, no published port, CONSTITUTION II.5), `api` (`CARDINAL_BOOKING_MCP_URL` pointed at `booking`), `web` (nginx reverse-proxying `/health`, `/sessions`, `/adapters`, `/mcp-apps`, `/demo` to `api`) |
| Config surface | `.env.example` — every variable any of `src/`, `web/src/`, `web/vite.config.ts` actually reads, none defaulted to a secret |
| `DEMO_MODE` reaches the real web app for the first time | `src/agent/demo_stream.py` (new) — `run_streamed_demo` drives the real phase machine/extractor/research dispatcher/P5 ranking through the *actual* `render_progress`/`render_tco`/`render_results`/`render_detail`/`open_booking_form` tool handlers (`for_audience(...).handler`, the same choke point a live tool call goes through), so DEMO_MODE finally pushes real A2UI/MCP-App messages over the real SSE transport instead of only mutating `SessionState` in memory (D-049) |
| Reactive checkout hand-off | `src/api/main.py`'s `mcp_app_rpc` calls `demo_stream.on_draft_submitted` (backgrounded, D-051) after a real `submit_booking_draft` RPC succeeds — checkout opens because a human's real click submitted the form, not because the script pre-decided it would |
| Score-breakdown click-through | `src/agent/demo_stream.py`'s `handle_explain_action`, wired from `session_actions`; `web/src/a2ui/catalog.tsx`'s `CarCard` now dispatches a real `explain` action on click (previously static markup with no handler at all) |
| `booking-mcp` as a real standalone service | `src/mcp/booking/http.py` — `BOOKING_MCP_HTTP_HOST`/`_PORT` env overrides so it can bind `0.0.0.0` in its own container; `src/api/main.py`'s `_ensure_booking_mcp_http` becomes a no-op when `CARDINAL_BOOKING_MCP_URL` is set |
| `Start Demo` control | `web/src/App.tsx` — fetches `/health`'s `demo_mode` flag, shows a button that `POST`s `/demo/{session}/start`; everything downstream (SSE canvas, MCP App host) was already wired by P6/P7 |
| Seven-beat e2e | `web/tests/demo-e2e.spec.ts` + `web/playwright.demo.config.ts` — walks the real product end to end, screenshotting each beat to `docs/screenshots/` (11 images) |
| Real gate | `scripts/gate_phase11.py` — replaces the PENDING stub; 11.1/11.2/11.5/11.6 against real Docker, 11.3/11.4 against a scrubbed-env disposable backend, 11.7 a same-file constant-resolving env-var scan, 11.10 a gate-0..10 sweep |
| Licence | `LICENSE` (MIT), DECISIONS.md D-047 recording the (confirmed clean-room) basis for not inheriting the user's other AGPL-3.0 repo's terms |
| Docs | `README.md` rewritten to PHASE-11 §5's order (paragraph, hero screenshot, run instructions, architecture, what's-real-vs-mocked table, requirement traceability table, licence); `docs/cardinal-deck.pptx` (10 slides); `docs/VIDEO-SCRIPT.md` (shot list, not yet recorded) |

Building the streamed demo driver exercised code paths gates 3/5 had only ever checked the
*shape* of, not the *content* of, and surfaced two real, pre-existing bugs neither gate's own
criteria happened to catch (DECISIONS.md D-050):

- `src/agent/extraction.py`'s `DemoSlotExtractor` read "we're planning to buy, not rent" as
  **RENT** — first-pattern-wins matching found "rent" appearing in the sentence at all, before
  ever checking for "buy". This has been silently true since Phase 3 landed (gate 3.1 only
  asserts a profile becomes *complete*, never that a slot holds the *correct* value); Family
  Fatima, one of gate 3.1's own ten personas, has been quietly researched as a renter the whole
  time. Fixed with a negation-stripping pass ahead of matching, plus a reordered
  explicitly-undecided pattern that could never have matched in its original position. New
  parametrised regression test, 11 cases:
  `tests/unit/test_agent_extraction.py::test_goal_extraction_reads_the_stated_option_not_the_ruled_out_one`.
- The top-ranked survivor under a buy goal is not always buy-eligible — `src/domain/ranking.py`'s
  `_reference_price` (P5, working exactly as designed) falls back to `market_value` for a
  rent-only listing, so it can rank and display a price without ever supporting a purchase
  quote. `demo_stream.py`'s booking beat now selects the first *buy-eligible* survivor in rank
  order rather than assuming rank 1 always matches the stated goal.
- A genuine race: pushing checkout's `mcp_app_open` SSE message immediately after a
  `submit_booking_draft` RPC succeeded (but before that RPC's own HTTP response reached the
  browser) tore down the outer iframe the response was still in flight to, via React remounting
  `McpAppHost` on the new message — `net::ERR_ABORTED`, caught only by running the real
  Playwright spec in a real browser (every curl-based check of the same backend logic passed,
  since curl never has an iframe to tear down). Fixed by backgrounding the hand-off and pacing
  it behind a short, deliberate delay (D-051).

None of gates 3/5's own criteria needed to change — both bugs were real and pre-existing, not
introduced by this phase, and both now have a regression test that would have caught them
in Phase 3/5 had it existed then.

### Deferred, deliberately

- **`[SCALE]` Public deployment** (PHASE-11 §2) — gate 11.11. No hosted instance exists; every
  criterion above is proven against a local Docker stack.
- **`[SCALE]` CI/CD with image publishing** (PHASE-11 §2) — nothing runs `make verify`/gate 11
  automatically on a push; no registry receives a built image.
- **`[SCALE]` `docs/ARCHITECTURE.md`, an ADR index, a contributor guide** (PHASE-11 §2) — the
  architecture diagram lives in the README and `plans/PLAN-00-OVERVIEW.md` §3; `DECISIONS.md`
  itself is the ADR log, just not indexed as one.
- **The demo video itself** — gate 11.9 half-passes: the deck is real and checked in, the shot
  list (`docs/VIDEO-SCRIPT.md`) is written against the same seven beats the e2e spec proves
  render, but recording a screen capture with narration is a human action no script here can
  perform.
- **Gate 11.8's clean-machine walkthrough** — by construction a human, on a machine that has
  never seen this repo, following `README.md`'s Run It section verbatim. Everything the rest of
  gate 11 can mechanically stand in for, it does; this one criterion it cannot.

---

## Phase 0 — Foundation ✅

Not the assignment, but Phase 1 could not stand without it: the `Listing` contract, the layering it
depends on, and the gate harness that runs both. Built to the point where P1's gate was meaningful,
then closed out fully once P3 gave 0.7 something to assert against.

```
  0.1    PASS     every domain model round-trips its fixture JSON      17 passed
  0.2    PASS     Money rejects float; arithmetic preserves Decimal     8 passed
  0.3    PASS     import-boundary scan finds zero violations            7 passed
  0.4    PASS     mypy --strict src/domain reports zero errors          11 source files
  0.5    PASS     specs/ holds constitution, spec, plan and tasks, all non-empty
  0.6    PASS     every gate script exists and runs to completion
  0.7    PASS     [SCALE] prompts live in files; no long prompt strings in src/
  7 passed, 0 failed, 0 pending  ->  GATE 0 GREEN
```

**0.7 closed when Phase 3 landed.** `prompts/` didn't exist because no prompt did until P3; the
criterion was written first (CONSTITUTION III.8) and started asserting the moment the six
`prompts/*.md` files and P3's own 200-char scan (gate 3.7, the same rule) appeared.

**0.5 closed 2026-08-08.** `uvx --from git+https://github.com/github/spec-kit.git specify init
--here --integration claude --script sh` was run against current spec-kit `HEAD` (`684b3d8e`),
which scaffolds `.specify/` (live templates + memory) and `.claude/skills/speckit-*` rather than
the flat, dot-command layout PHASE-0 §7 was written against. `specs/constitution.md`, `spec.md`,
`plan.md`, and `tasks.md` were authored by hand against the installed templates —
`.specify/templates/{constitution,spec,plan,tasks}-template.md` — with real Cardinal content (the
domain contracts, the phase map, the twelve phases' actual exit-gate criteria), not placeholder
text. `.specify/memory/constitution.md` carries an identical copy, since that's the path the
`speckit-*` skills read/write at runtime if invoked later. See `DECISIONS.md` D-011 for why the
gate script's flat-path check was kept as-is rather than rewritten to match the tool's nested
default.

All twelve `[MVP]` domain models from PHASE-0 §4 exist and round-trip. `tests/test_layer_boundary.py`
now requires `domain`, `adapters`, `mcp` and `agent` all four — `agent` joined when P3 landed.

---

## Verification, as run

Two different runs, deliberately shown separately — they exercise different amounts of the stack:

```
# 2026-08-07, docker compose up (Postgres 16 + pgvector live)
ruff check src tests scripts          All checks passed!
ruff format --check                   57 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/adapters src/api             Success: no issues found in 19 source files
pytest tests -q                       133 passed, 3 skipped
gates 0..11                           all exit 0

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after closing gate 0.5
ruff check src tests scripts          All checks passed! (one pre-existing unsorted import in
                                       src/mcp/audience.py fixed in passing)
ruff format --check                   60 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/adapters src/api             Success: no issues found in 19 source files
pytest tests -q                       107 passed, 29 skipped
gates 0..11                           all exit 0 (0 GREEN w/ 1 pending, 1 GREEN, 2..11 PENDING-by-design)

# 2026-08-08, no container — after Phase 2 (MCP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   75 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/adapters src/api src/mcp     Success: no issues found in 33 source files
pytest tests -q                       133 passed, 29 skipped
gates 0..11                           all exit 0 (0 GREEN w/ 1 pending, 1 GREEN, 2 GREEN w/ 1 pending,
                                       3..11 PENDING-by-design)

# 2026-08-08, docker compose up -d postgres (Postgres 16 live) — after Phase 3 (Agent) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   92 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 44 source files
pytest tests -q                       232 passed, 3 skipped
gates 0..3 --require-stack            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN
gates 4..11                           all PENDING-by-design, exit 0

# 2026-08-08, docker compose up -d postgres (Postgres 16 live) — after Phase 4 (Memory, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   95 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 45 source files
pytest tests -q                       248 passed, 3 skipped
gates 0..4 --require-stack            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN,
                                       4 GREEN w/ 5 pending
gates 5..11                           all PENDING-by-design, exit 0

# 2026-08-08, docker compose up -d postgres (Postgres 16 live) — after Phase 5 (Reasoning, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   103 files already formatted
mypy --strict src/domain              Success: no issues found in 14 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 45 source files
pytest tests -q                       306 passed, 3 skipped
gates 0..5 --require-stack            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN,
                                       4 GREEN w/ 5 pending, 5 GREEN w/ 1 pending
gates 6..11                           all PENDING-by-design, exit 0

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after Phase 6 (Generative UI, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   116 files already formatted
mypy --strict src/domain              Success: no issues found in 14 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 52 source files
pytest tests -q                       310 passed, 37 skipped
gates 0..6                            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1 pending,
                                       4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6 GREEN w/ 1 pending
gates 7..11                           all PENDING-by-design, exit 0
web/: npx tsc -b --noEmit             clean, no errors
web/: npx playwright test             6 passed (golden-fixture render, zero console errors)

# 2026-08-08, docker compose up (Postgres 16 live) — after Phase 7 (MCP Apps) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   122 files already formatted
mypy --strict src/domain              Success: no issues found in 14 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 57 source files
pytest tests -q                       321 passed, 37 skipped
gates 0..7                            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1 pending,
                                       4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6 GREEN w/ 1
                                       pending, 7 GREEN
gates 8..11                           all PENDING-by-design, exit 0
web/: npx tsc -b --noEmit             clean, no errors
web/: npx playwright test (gate 6)    6 passed (render.spec.ts only -- testMatch keeps gate 7's
                                       mcp-apps.spec.ts out of this run and vice versa)
web/: npx playwright test (gate 7)    10 passed (web/tests/mcp-apps.spec.ts, one per criterion)

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after Phase 8 (Commerce) landed
ruff check src tests scripts          All checks passed! (one pre-existing unsorted import in
                                       src/agent/demo.py fixed in passing)
ruff format --check                   136 files already formatted
mypy --strict src/domain              Success: no issues found in 16 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 64 source files
pytest tests -q                       374 passed, 40 skipped
gates 0..8                            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1
                                       pending, 4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6
                                       GREEN w/ 1 pending, 7 GREEN, 8 GREEN
gates 9..11                           all PENDING-by-design, exit 0
web/: npx tsc -b --noEmit             clean, no errors
web/: npx playwright test (gate 6)    6 passed
web/: npx playwright test (gate 7)    10 passed
web/: npx playwright test (gate 8)    4 passed (web/tests/commerce.spec.ts, one per browser
                                       criterion)

Also re-run with `docker compose up -d postgres` live and `CARDINAL_DATABASE_URL` set, migration
`0002_bookings_commerce` applied: `pytest tests -q` → 411 passed, 3 skipped (the 3 remaining
skips are `mock_autobazaar`'s rental-only contract cases, unrelated to a container); gates 0..8
with `--require-stack` where applicable all GREEN, including
`tests/integration/test_adapters_booking_store_postgres.py` (3 tests, otherwise skipped).

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after Phase 9 (Observability) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   139 files already formatted
mypy --strict src/domain              Success: no issues found in 16 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 65 source files
pytest tests -q                       398 passed, 40 skipped
gates 0..9                            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1
                                       pending, 4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6
                                       GREEN w/ 1 pending, 7 GREEN, 8 GREEN, 9 GREEN w/ 2 pending
gates 10..11                          all PENDING-by-design, exit 0

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after Phase 10 (Trust, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   142 files already formatted
mypy --strict src/domain              Success: no issues found in 17 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 65 source files
pytest tests -q                       519 passed, 40 skipped
gates 0..10                           0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1
                                       pending, 4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6
                                       GREEN w/ 1 pending, 7 GREEN, 8 GREEN, 9 GREEN w/ 2
                                       pending, 10 GREEN w/ 5 pending
gate 11                               PENDING-by-design, exit 0
web/: npx playwright test (gate 6)    6 passed
web/: npx playwright test (gate 7)    10 passed
web/: npx playwright test (gate 8)    4 passed
```

```
# 2026-08-08, docker compose up (real 4-service stack: postgres/api/booking/web) — after
# Phase 11 (Delivery, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   143 files already formatted
mypy --strict src/domain              Success: no issues found in 17 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 66 source files
pytest tests -q                       530 passed, 40 skipped
gates 0..11                           0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1
                                       pending, 4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6
                                       GREEN w/ 1 pending, 7 GREEN, 8 GREEN, 9 GREEN w/ 2
                                       pending, 10 GREEN w/ 5 pending, 11 GREEN w/ 3 pending
web/: npx tsc -b --noEmit             clean, no errors
web/: npx playwright test (gate 6)    6 passed
web/: npx playwright test (gate 7)    10 passed
web/: npx playwright test (gate 8)    4 passed
web/: npx playwright test (gate 11)   1 passed (web/tests/demo-e2e.spec.ts, all seven beats +
                                       the audit-log trace, screenshotted to docs/screenshots/)
```

The jump from 519 to 530 passed is Phase 11's new `tests/unit/test_agent_extraction.py`
regression coverage (11 parametrised cases) for D-050's goal-extraction negation bug — found
while building `src/agent/demo_stream.py`, not introduced by it. Nothing else regressed: every
test that existed before Phase 11 still passes unchanged; gate 8's 8.7 evidence changed from
148 to 149 files scanned purely because the repo now has one more file in the scanned tree
(`src/agent/demo_stream.py` itself), not from a denylist behaviour change.

The jump from 398 to 519 passed is Phase 10's new `tests/unit/test_domain_trust.py` (11:
`detect_injection`, `escape_untrusted_text`, `wrap_listing_content`, including the
delimiter-escape/note-leak case D-042 records) and `tests/unit/test_agent_injection_corpus.py`
(corpus-parametrised over all 30 entries three ways — score purity, rationale/grounding
purity, wrapper-tag integrity — plus classifier-recall checks on the three plainly-worded
categories and two tool-shape/end-to-end memory-poisoning tests), plus one new test in
`tests/unit/test_mcp_marketplace.py` for `get_listing`'s wrapped output. Nothing regressed:
every test that existed before Phase 10 still passes unchanged. Gate 8's 8.7 evidence changed
(148 files scanned, was 142) purely from sharing its scan mechanism with gate 10.3
(DECISIONS.md D-044), not from a behaviour change; gates 2.2/2.5 (tool count, `get_listing`
token size) still pass but their printed numbers shift slightly (15 tools unchanged from P8,
`get_listing` now 354 tokens vs. 327 — still well inside gate 2.5's 800-token cap) because
`get_listing`'s `description` field is now the wrapped string, not the raw one.

The jump from 374 to 398 passed is Phase 9's new `tests/unit/test_agent_tracing.py` (14 tests:
redaction, span shape, phase/session trace-id nesting, subagent-span parenting and overlap,
PII-before-a-captured-span redaction) and `tests/unit/test_agent_evals.py` (10 tests:
`_violates_constraints`/`_satisfies_profile` unit cases plus three eval-harness integration
tests against the 10-persona extra fixture). Nothing regressed: every test that existed before
Phase 9 still passes unchanged; gate 1's docker-compose container being already up from earlier
in the session is why it reports a hard `PASS` rather than `PENDING` in this run without
`CARDINAL_DATABASE_URL` explicitly set — the same `--require-stack`-independent probe 1.10 has
always used when something is actually listening on the expected port.

Gate 1 shows `backend=postgres` this run (the container was already up from earlier the same
session, not started fresh for this pass) — the same code path 1.10's `--require-stack` run
exercises. Gate 3's 3.2 and gate 4's 4.1 report `PENDING` rather than `PASS` in the `gates 0..7`
line above because that pass ran without `--require-stack`; both are unchanged since their own
phases landed and are not re-verified here.

The jump from 321 to 374 passed is Phase 8's new `tests/unit/test_domain_{booking,financing}.py`,
`tests/unit/test_adapters_{payments,booking_store}.py` (36 tests), plus `tests/unit/
test_mcp_booking.py`'s rewrite from P7's four-tool-stub-pinning shape to nineteen tests covering
the real `open_checkout`/`mint_gesture_token`/`confirm_booking` behaviour (the same treatment P6
gave P2's `ui-mcp` stub tests). `tests/integration/test_adapters_booking_store_postgres.py` (3
tests) only runs with a container, accounting for part of the no-container/live-container skip
gap. Nothing regressed: every test that existed before Phase 8 still passes unchanged, and gate
2.2's tool count moved from 14 to 15 (booking-mcp's new `mint_gesture_token`) — the only P2 gate
arithmetic P8 had to touch, not a P2 regression.

The jump from 310 to 321 passed is Phase 7's new `tests/unit/test_mcp_apps.py` (8 tests) plus
three new tests added to `tests/unit/test_mcp_booking.py` (`test_open_booking_form_pushes_a_
mount_app_message_through_the_sink`, `test_submit_booking_draft_is_idempotent_per_draft_id`,
`test_booking_form_resource_is_registered_with_declared_csp`) — 11 new, net of zero removed.
Nothing regressed: every test that existed before Phase 7 still passes unchanged.

The jump from 248 to 306 passed is Phase 5's 58 new `tests/unit/test_domain_{scoring,costs,
tco,ranking}.py` tests. `pytest tests -q` with no container (`CARDINAL_DATABASE_URL` unset)
still passes 272 (37 skipped) — every P5 test is pure/deterministic and needs no database,
same as the rest of `src/domain`. Nothing regressed at any step; gate 5 itself needs no
container at all (all ten criteria are pure or deterministic code, D-015's reasoning applied
to P5).

The jump from 272 to 310 passed (both "no container" runs) is Phase 6's new
`tests/unit/test_ui_{validate,compiler,actions}.py` and `tests/integration/test_api_ui.py`,
net of `tests/unit/test_mcp_ui.py`'s five old P2 stub-pinning tests, which P6 rewrote entirely
to exercise the real compiler-backed handlers instead. Nothing regressed: every test that
existed before Phase 6 still passes unchanged.

The 3 skips (all runs) are `mock_autobazaar` sitting out three rental-only contract tests — a
dealer adapter has no rentable listings to price. They are selected on `adapter.kind`, never on
the adapter's name.

The 26 (30 from Phase 3, 34 from Phase 4) integration tests skip instead when
`CARDINAL_DATABASE_URL` is unset, so `make test` runs with no container — that accounts for the gap
between the container runs' 3 skipped and the no-container runs' 29 skipped. The jump from 107 to
133 passed between the second and third runs is Phase 2's 25 new `tests/unit/test_mcp_*` tests
landing; the jump from 133 to 232 in the fourth run is Phase 3's 66 new `tests/unit/test_agent_*`
tests plus 4 new Postgres-backed session-store tests; the jump from 232 to 248 in the fifth run is
Phase 4's 13 new `tests/unit/test_agent_journal.py` tests plus 4 new Postgres-backed decision-
journal tests (`tests/integration/test_agent_journal_postgres.py`), run with the container up.
Nothing regressed at any step.

### Environment notes

- Python 3.14 on Windows. `psycopg`'s async mode rejects the default `ProactorEventLoop`, so every
  database entry point goes through `run_async` in `src/adapters/db/session.py`, and the test suite
  selects a `SelectorEventLoop` via pytest-asyncio's `pytest_asyncio_loop_factories` hook. This
  does *not* cover `uvicorn src.api.main:app` run directly on native Windows (outside Docker) --
  uvicorn creates and owns its own event loop before any of our code runs, so `run_async` has
  nothing to wrap; discovered when Phase 8's gate spawned a real `uvicorn` subprocess that
  actually touched Postgres for the first time. `docker compose up`'s `api` container is Linux
  and unaffected; this only bites a bare `python -m uvicorn ...` on Windows against a live
  `CARDINAL_DATABASE_URL`, which no documented workflow (`make dev` included, in its usual
  `DEMO_MODE`/in-memory posture) currently exercises.
- `docker compose up` was verified cold, from a removed volume: alembic ran `0001_initial`, the seed
  wrote 240 rows, `/health` returned 200.
- `web/`'s toolchain: Node v24, npm. `@a2ui/react`'s published package nests its own copy of
  `@a2ui/web_core`; without `web/package.json`'s `"overrides": {"@a2ui/web_core": "0.9.1"}` a
  fresh `npm install` produces two type-incompatible copies (DECISIONS.md D-027). Playwright's
  Chromium build was already present on this machine (`npx playwright install chromium` is a
  no-op if so, otherwise a ~150 MB download) — gate 6.2 reports `PENDING` rather than failing
  when `web/node_modules` doesn't exist yet.

---

## Live path — first real rehearsal (2026-08-08)

The live orchestrator ran end-to-end against a real model for the first time, in a browser, with
`DEMO_MODE=false` and a real `ANTHROPIC_API_KEY`. This is the rehearsal every phase entry from
P3 onward listed as "deferred, deliberately" (D-015). It found four defects, all of them in code
that typechecked, passed 530 tests, and had never been executed:

| Defect | Fix | Recorded |
|---|---|---|
| No chat transport at all — `orchestrator.send()` had no HTTP route, and `web/` had no text input. `DEMO_MODE=false` rendered a blank page with nothing clickable. | `POST /sessions/{id}/messages` + a real composer in `web/src/App.tsx` | — |
| `prompts/` missing from the runtime image; `prompts.py` resolved it relative to a source checkout. Every live turn died at the first `load_prompt`. | Dockerfile copies `prompts/`; `PROMPTS_DIR` falls back to cwd | D-053 |
| A new `ClaudeSDKClient` per turn with a pinned session id — `Session ID ... is already in use` on every turn after the first, and no conversation memory even in principle. | One long-lived connected client per session, per-session lock | D-052 |
| The A2UI canvas stayed empty because the system prompt never told the model to render to it. | `prompts/orchestrator_system.md` now names when each `render_*` tool is expected | D-054 |

Also added, not a defect fix: assistant text and tool activity now stream to the browser over
the existing SSE channel as the turn runs (`agent_text`/`agent_status`, discriminated the same
way `mcp_app_open` already is), because a live turn takes tens of seconds and a static spinner
for that long is indistinguishable from a hang.

Two more defects surfaced only once a browser drove the deployed image, both invisible to curl:

| Defect | Fix | Recorded |
|---|---|---|
| nginx's 60s default `proxy_read_timeout` cut off a ~72s turn as a 504. The UI showed a failed message while the backend answered fine seconds later. Direct `curl` to `:8000` bypassed nginx and never saw it. | `proxy_read_timeout 300s` on `/sessions/` in `web/nginx.conf` | — |
| Every subagent's traffic streams through `receive_response()`, including the `UserMessage` carrying the prompt it was launched with — so the `interviewer`'s system prompt was published into the chat rail as if the agent had said it. | `_progress_events`/`_extract_assistant_text` now take text only from top-level `AssistantMessage`s (`parent_tool_use_id is None`) | — |

**Model routing is now env-selectable and defaults to the cheap tier** (D-055).
`CARDINAL_AGENT_MODEL` / `_EFFORT` / `_THINKING` default to `claude-haiku-4-5` / `low` /
`disabled`; PLAN-00 §6.7's `claude-opus-5` / `high` / `adaptive` is one uncommented block in
`.env`. Measured on the same INTERVIEW turn: **~72s on the plan's routing, ~5s on the default.**

The weaker default model is also a better prompt test than the strong one, and it earned its
keep immediately: it skipped the `render_*` canvas tools Opus called unprompted, and it narrated
its own delegation ("I've launched the interviewer") instead of asking the questions. Both were
unstated expectations in `prompts/orchestrator_system.md` — now stated (D-055's closing note).

`DEMO_MODE` was removed from the product UI in the same pass — there is one real path now, not a
demo path plus a live path. `POST /demo/{id}/start` still exists and is still gated on
`DEMO_MODE=true`; nothing in `web/` calls it.

---

## Alternate INTERVIEW-phase models + a full re-proof of the demo path (2026-08-08)

**Model selection (D-056).** `GET /models` + `POST /sessions/{id}/model` let a session pick
Groq/Gemini/OpenRouter/OpenAI for the INTERVIEW phase's conversational Q&A only —
`src/agent/providers.py` (plain `httpx`, no SDK) + `src/agent/interview_chat.py` (one call per
turn, folded through the existing `process_turn` so phase-transition logic is unchanged). The
moment `Phase` advances past INTERVIEW, the session falls through to the untouched
`CardinalOrchestrator.send()` — every MCP tool, every subagent, every guardrail, `confirm_booking`'s
invisibility, all exactly as before — primed once with what the alternate model already gathered.
Verified live end-to-end against Groq's free tier (zero Anthropic spend): correct slot extraction,
correct hand-off, RESEARCH starting with the right numbers and no re-asked questions. Reasoning
models (Qwen) need `<think>` stripped before their JSON parses — the same fix
`D:\Interview Agent`'s own `llm_router.py` already carries for the identical failure.

**Re-proving the demo path found two packaging bugs older than this session (D-057).** Asked to
show the PowertrainExplainer 3D view and the checkout/payment gateway working, `demo-e2e.spec.ts`
(gate 11.3/11.4) failed on beats it had never failed on before:

| Defect | Fix |
|---|---|
| The new `GET /models` route's nginx location was a *prefix* match, so it also swallowed the older, unrelated static path `/models/powertrain/*.glb` into a 404 — `<model-viewer>` had nothing to load and rendered as a silent empty box. | `location = /models` (exact match) in `nginx.conf`; equivalent `bypass` fix in `vite.config.ts`'s dev proxy |
| `booking-mcp`'s static resource HTML (`booking_form.html`, `checkout.html`) was never declared as package data, so `pip install .` silently dropped it — same category of bug as D-053's `prompts/`, first caught here because this was the first time `resources/read` ran against the *installed* package rather than a checkout. | `[tool.setuptools.package-data]` in `pyproject.toml` |

Gate 11 re-run clean after both fixes: **8 passed, 0 failed, 3 pending** (11.8 needs a human,
11.9 needs a recorded video, 11.11 is `[SCALE]`) — all seven demo beats, including the 3D viewer
and the sandboxed checkout with its financing calculator and mock-payment banner, screenshotted
fresh under `docs/screenshots/`. `demo-e2e.spec.ts`'s beat-1 trigger was updated from clicking the
now-removed "Start Demo" button to a direct `POST /demo/{id}/start` call, matching D-055's UI
redesign rather than reverting it.

---

## Qwen as the default interview model, per-listing 3D, and a real demo script (2026-08-08)

**Model picker is now hidden by default; Qwen 3.6 (Groq, free) is the INTERVIEW-phase default**
(D-059). `CardinalOrchestrator.model_for` resolves `CARDINAL_INTERVIEW_MODEL` (default
`groq/qwen/qwen3.6-27b`) instead of hardcoding Claude; `GET /models` returns `[]` unless
`CARDINAL_SHOW_MODEL_PICKER=true`, and `App.tsx`'s existing `models.length > 1` guard means the
picker UI needed no code change to disappear — one backend flag, not two switches to keep in sync.
Two real bugs fell out of scripting real conversational turns against Qwen rather than
hand-fed JSON (D-058): no anchor for "today" (a relative-date turn burned its whole token
budget deliberating inside an unclosed `<think>` block and returned nothing), and `<think>`
stripping alone can't recover text that was never emitted — `providers.chat` now passes Groq's
`reasoning_format="hidden"` for any model `model_catalog` flags `reasoning: True`, which keeps
the chain of thought out of `content` structurally rather than filtering it after the fact.

**Per-listing 3D on result cards** (D-060), distinct from P6's per-archetype
`PowertrainExplainer`: `src/mcp/ui/vehicle_models.py`'s three-tier resolver (real per-vehicle
GLB → body-style silhouette → powertrain cutaway, always resolves to *something*) feeds a new
`CardVisual` the `render_results` handler attaches per listing, kept out of the compiler itself
(PHASE-6 SS4's purity constraint) the same way `render_detail`'s headline already is. 28 cars in
`VEHICLE_SLUGS` were derived, not guessed — verified as exactly what the demo script's eight
scripted openers put on screen against the real seeded store, not assumed from catalogue
frequency (the most-listed models in the seed are largely unfindable as downloadable 3D
assets). None are sourced yet (`scripts/check_vehicle_assets.py` reports 0/28); every card
degrades to a real, present, placeholder-cube silhouette (`scripts/generate_silhouette_assets.py`,
12/12 present) rather than an empty box, so the feature is fully functional today and sourcing
real models is purely additive.

**`docs/DEMO-SCRIPT.md`** is what to actually say to the product: a five-minute guided run plus
eight alternate openers, each pinned to real listings/prices from the seeded catalogue (not
illustrative numbers), a 3D-asset sourcing guide with the exact 28-car table and a licensing/size-
budget note (gate 6.7's 16 MB cap means every sourced model needs decimating — a raw download
does not fit), and two known-fixed edge cases (a relative-date turn, an impossible ask) worth
demonstrating deliberately.

**Full re-verification after all of the above:** lint/typecheck/571 tests green, frontend build
clean, gate 6 green (9/9 + 1 `[SCALE]` pending), gate 11 green (8/8 + 3 pending, none new),
`.env.example` gate (11.7) now covers `CARDINAL_INTERVIEW_MODEL`/`CARDINAL_SHOW_MODEL_PICKER`
too. Live-confirmed: `GET /models` → `[]`, a plain interview turn on the Groq default responds
in ~3s with no picker, no leaked model name, and no cost beyond Groq's free tier.

---

## RESEARCH never advanced in the live path (2026-08-08)

**A real bug, reported live, reproduced, fixed, only partially re-confirmed (D-062).** The
handoff-primed live path (Groq INTERVIEW → Claude RESEARCH) got stuck after "searching both
marketplaces..." with no results ever rendering. Cause: `phase_machine.advance()` -- what moves
`Phase` from RESEARCH to RECOMMEND once candidates exist -- was never called anywhere in the
live path; `demo.py`/`demo_stream.py` drive it procedurally for their scripted paths, but
`orchestrator.py`'s `send()` had no equivalent. The live model correctly never called
`render_results` (its own prompt reserves that for RECOMMEND), because nothing ever told its
phase context RESEARCH was done. Fixed with `build_phase_advance_hook`, a `PostToolUse` hook
mirroring the existing `PreToolUse` audit hook's pattern.

**The first two versions of that fix were both wrong (D-066).** Each guessed at the shape of
`PostToolUse`'s `tool_response` and each silently extracted nothing from searches that had
really found cars — the same empty canvas, now caused by the fix rather than its absence. With
the Anthropic cap blocking a third live attempt, the shape was instead read straight out of the
bundled CLI binary (`grep -a` over `claude.exe`), which builds the payload itself:
`tool_response` is the tool_result block's **`content`** — for an MCP tool, a *bare list* of
content blocks, not a dict wrapping a `content` key. Both earlier versions keyed off the dict
form, so a bare list fell through and returned nothing every time.

**And the parser was not the last of it (D-067).** With credits restored, the first real
rehearsal found three more defects stacked behind each other, none visible from a source
checkout, each uncovered by *printing what the live path actually did* rather than reasoning
about it:

| # | Defect | Fix |
|---|---|---|
| 1 | Guardrails matched bare tool names; live tools arrive namespaced (`mcp__market__search_cars`). The phase hook, the audit hook's denial, and gate 3.8's backstop all silently never matched. | `base_tool_name()` normalises — the same `rsplit` `_progress_events` already did |
| 2 | The prompt told the orchestrator to delegate searching to two `researcher` subagents; the `Agent` tool launched them **asynchronously** and the turn ended before any had searched. The person was answered before a result existed. | Prompt now calls `search_cars` directly and waits (it already queries every marketplace, D-013); the hook is replaced by `extract_candidate_ids`, a scan of the finished turn's message stream |
| 3 | The audit hook looked state up by the **CLI's** session id, not the app's — so `_filled_required_count` always read 0. Latent forever; fix (1) *activated* it, and it then blocked every live search with "no RequirementProfile has been started". | Bind the app `session_id` up front, exactly as `build_search_gate` always did |

**Verified live, end to end — the thing outstanding since D-015.** A real session now runs
INTERVIEW (Groq) → handoff → RESEARCH (Claude) → phase advances to `recommend` with 7 real
candidates → **7 `CarCard`s render on the canvas** with real scores and rationales (a 2024
Toyota RAV4 GT-Line at €23,003.83, score 9.20, citing its €6,996 budget headroom), zero page
errors. Screenshotted; gate 3 green.

Worth carrying forward: fix (1) *created* symptom (3) — unblocking one guardrail activated
another that had never run. Changes in this layer need re-verifying live, not assuming.

RECOMMEND → TRANSACT may still have the same shape of gap (`selected_candidate` in the live
path) — now testable, not yet exercised.

---

## Next

Every `[MVP]` line in every phase, including Phase 11, is now green — `docker compose up` on a
clean-ish machine (untouched `.env.example`) brings up the full four-service stack and the whole
seven-beat demo runs with zero API keys. What's left is the `[SCALE]` backlog (deferred per
CONSTITUTION III.3, none of it blocking) and the handful of things only a human, a live model, or
a second machine can actually do:

1. **Record the demo video** (`docs/VIDEO-SCRIPT.md`'s shot list, gate 11.9's other half) and
   **run gate 11.8 for real** — a person who didn't write this repo, on a machine that's never
   seen it, following `README.md`'s Run It section verbatim. Both are structurally impossible for
   this session to complete itself; everything mechanical gate 11 could stand in for, it does.
2. **A live rehearsal of `src/agent/orchestrator.py`** against the real `claude` CLI, with
   `ANTHROPIC_API_KEY` set, at least once — the wiring is real and type-checked but has only been
   exercised through `DEMO_MODE`'s deterministic path so far (DECISIONS.md D-015). This should
   be the first time a live session calls `rank()` with a model-chosen `WeightSet`, the first
   time `render_results`/`compose_surface`/`open_booking_form`/`open_checkout` are called from
   inside a real conversation rather than a gate script or test, the first time a judge's own
   trusted click — not Playwright's simulated one — reaches `confirm_booking`, and the first
   time `ClaudeAgentSDKInstrumentor`'s auto-generated spans and a real Langfuse export
   (`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`) get exercised outside `src/agent/tracing.py`'s
   own unit tests.
3. **Phase 8's own deferred items** — a real `PaymentGateway` behind the mock's protocol seam
   (feature-flagged, `[SCALE]`), refund/cancellation tool surfaces for the `CANCEL`/`ABANDON`
   transitions the state machine already supports, and the native-Windows `uvicorn`+Postgres
   event-loop gap noted above (Docker-only impact today).
4. **Phase 9's `[SCALE]` tier** — prompt-cache hit-rate tracking (gate 9.8), CI-gated eval
   regression detection (gate 9.9), per-session cost budget + hard cap, the reasoning-replay
   timeline in-product, online evals on sampled real sessions — deferred per CONSTITUTION
   III.3; all need a live session to threaten a budget or produce a cache signal against.
5. **Phase 5's `[SCALE]` tier** — constraint relaxation / counterfactuals on infeasibility
   (gate 5.10), weight calibration against outcome data, regional tax/insurance/energy tables —
   deferred per CONSTITUTION III.3.
6. **Phase 6's `[SCALE]` tier** — `Vehicle360`, progressive/streaming render, reduced-motion +
   full a11y pass (gate 6.10), real `PowertrainExplainer` geometry to replace the placeholder
   GLBs (D-028) — deferred per CONSTITUTION III.3.
7. **Phase 4's `[SCALE]` tier (4.4-4.8)** — episodic memory, semantic/pgvector retrieval,
   consolidation/contradiction/staleness, drift detection, `forget_me` — deferred per
   CONSTITUTION III.3 (DECISIONS.md D-019). `forget_me` (gate 4.8) now also needs to erase
   from Langfuse, per IV.3 -- P9 gives it somewhere real to erase from. This is now the only
   remaining `[SCALE]` backfill target that isn't Phase 10's own (item 9 below) or Phase 9's
   (item 4 above) — the episodic-memory tier gate 10.2/10.5 both currently lean on being
   correctly unbuilt.
8. Keep `specs/{spec,plan,tasks}.md` current as phases land — CONSTITUTION V (spec-kit
   governance) treats them as living artifacts, not a one-time exercise. `PROGRESS.md` stays the
   sole source of truth for status either way.
9. **Phase 10's `[SCALE]` tier** — PII redaction for logs + the memory tier (gate 10.5, half
   already done via P9's gate 9.6), two-tenant isolation (gate 10.6, a schema migration once
   a second tenant is real), `pip-audit`/`npm audit` in CI (gate 10.7), `docs/ATTRIBUTION.md`
   (gate 10.8, nothing to attribute until P6's placeholder GLBs are replaced), and
   `docs/THREAT-MODEL.md` as a standalone gated file (gate 10.9, the content already exists
   in `plans/PHASE-10-TRUST.md` §8) — deferred per CONSTITUTION III.3.
10. **Phase 11's `[SCALE]` tier** — a public deployment (gate 11.11), CI/CD with image
    publishing so `make verify`/gate 11 run on every push instead of only locally, and
    `docs/ARCHITECTURE.md` + an ADR index + a contributor guide (the content exists today,
    split across the README, `plans/PLAN-00-OVERVIEW.md`, and `DECISIONS.md`; none of it is
    indexed as those specific artifacts yet) — deferred per CONSTITUTION III.3.
