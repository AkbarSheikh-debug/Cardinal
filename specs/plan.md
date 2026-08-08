# Implementation Plan: Cardinal — MVP

**Branch**: `000-cardinal-mvp` | **Date**: 2026-08-08 | **Spec**: [`specs/spec.md`](spec.md)

**Input**: Feature specification from `specs/spec.md`

**Note**: Full phase-by-phase detail lives in `plans/PLAN-00-OVERVIEW.md` and `plans/PHASE-*.md`;
this file is the spec-kit-shaped summary of the same plan, kept in sync with it rather than
duplicating its reasoning. Where the two could drift, `plans/PLAN-00-OVERVIEW.md` is authoritative
for architecture and `PROGRESS.md` is authoritative for what is actually built.

## Summary

Cardinal interviews a car buyer or renter into a typed `RequirementProfile`, searches mock rental
and dealership marketplaces through a common adapter protocol, ranks results with a deterministic,
model-weighted / code-scored engine whose every claim is grounded in a cited listing field, and
lets the user complete a booking and mock payment inside the conversation via sandboxed MCP Apps —
with confirmation structurally reachable only by an explicit human click. Primary technical
approach: layered Python backend (`domain` → `adapters` → `agent` → `mcp` → `api`) driven by the
Claude Agent SDK, a React + A2UI frontend, PostgreSQL + pgvector for storage, and OpenTelemetry →
Langfuse for observability — all runnable from `docker compose up` with zero API keys in
`DEMO_MODE`.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript / React 19 (frontend, Vite)

**Primary Dependencies**: Claude Agent SDK (Python) for orchestration, subagents, in-process MCP
servers, and hooks; FastAPI + Pydantic v2 for transport; `@a2ui/react` for the generative-UI
renderer; `<model-viewer>` for the powertrain explainer

**Storage**: PostgreSQL 16 + pgvector — listings, sessions, journal, and embeddings in one
container; no second datastore

**Testing**: pytest (unit, contract, integration), Playwright (e2e, MCP App sandbox / gesture-token
assertions), a scripted 10/20/30-persona harness for interview, ranking, and injection gates

**Target Platform**: Linux containers via `docker compose`; local dev on Windows/macOS/Linux
through `make dev`

**Project Type**: Web application (FastAPI backend + Vite/React frontend), single repository

**Performance Goals**: Search results ≤4000 tokens / ≤20 items; per-item detail ≤800 tokens; cost
per full session ≤ $0.40 across the golden persona set (`[SCALE]` target, tracked from P9 on)

**Constraints**: No real payment gateway or provider identifier anywhere in the repo (I.1); no
booking confirmable without a trusted client gesture (I.2); `src/domain` and `src/agent` import no
`fastapi`, and `src/domain` touches no network/DB/clock (II.1); ranking must be bit-for-bit
deterministic given the same profile and seed (II.2)

**Scale/Scope**: ≥100 seeded listings across ≥10 categories, ≥10 brands per category (currently
240/12/12+ — see `PROGRESS.md`); twelve phases (`P0`–`P11`) covering foundation through delivery

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against `.specify/memory/constitution.md` v1.0.0:

| Principle | Check | Status |
|---|---|---|
| I. Safety Is Structural, Not Prompted | `confirm_booking` is `visibility: ["app"]`-only by design (P8); no payment SDK is planned as a dependency anywhere in `pyproject.toml` | PASS (design-level; enforced at P8/P10 gates) |
| II. Domain Purity & Deterministic Reasoning | Layering in §Project Structure below keeps `src/domain` I/O-free; scoring lives entirely in `src/domain/scoring.py`, weights come from the model, scores from code (P5) | PASS |
| III. Gates Are Run, Not Read | Every phase ends in `scripts/gate_phaseN.py`; `PROGRESS.md` is the sole state record | PASS (mechanism exists — `gate_phase0.py` §0.6) |
| IV. Privacy By Construction | Redaction hook is planned in the OTel export path (P9), not as a post-hoc scrub; tenant filtering is planned inside queries, not post-fetch (P10) | PASS (design-level; enforced at P9/P10 gates) |
| V. Spec-Driven, Progress-Tracked | This plan and its sibling artifacts exist under `specs/`; `PROGRESS.md` is updated as phases close, never the `plans/PHASE-*.md` docs | PASS |

No violations requiring an entry in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/
├── constitution.md      # This project's spec-kit governance summary (points to root CONSTITUTION.md)
├── spec.md               # Feature specification (this feature = the whole hackathon MVP)
├── plan.md                # This file
└── tasks.md               # Phase-grounded task list (see specs/tasks.md)
```

Deeper per-phase design detail (research, data model, contracts) already exists as committed prose
in `plans/PHASE-0-FOUNDATION.md` through `plans/PHASE-11-DELIVERY.md` rather than being
re-generated under `specs/000-cardinal-mvp/`; spec-kit's usual `research.md` / `data-model.md` /
`contracts/` outputs are the phase docs' §3–§9 sections for this project.

### Source Code (repository root)

```text
src/
├── domain/          # pure Python: Listing, Money, RequirementProfile, Scorer, TcoEngine. No I/O.
├── adapters/         # marketplace adapters, embeddings, storage. Imports domain only.
│   ├── mock/            # MockDriveNow, MockAutoBazaar
│   ├── catalogue/        # taxonomy + seeded-catalogue generator
│   └── db/               # Postgres session/store
├── agent/            # orchestration, subagents, prompts, memory. Imports domain + adapters.
│                      # ⚠ never imports fastapi — must run from a plain script.
├── mcp/               # marketplace-mcp, ui-mcp, booking-mcp servers; owns ui:// resources
└── api/                # FastAPI. Transport only — routes, SSE, auth.

web/                  # Vite + React 19 — chat rail, A2UI canvas, MCP App host
prompts/               # versioned .md prompt files — never inline strings over 200 chars
scripts/gate_phase{0..11}.py
tests/
├── unit/ contract/ integration/ e2e/
docs/                  # THREAT-MODEL.md, ARCHITECTURE.md, deck, video
```

**Structure Decision**: Single repository, layered backend (Option 1 shape, web application
variant) — `src/domain` → `src/adapters` → `src/agent` → `src/mcp` → `src/api`, plus a separate
`web/` frontend. This is already built and enforced by `tests/test_layer_boundary.py` and a ruff
`flake8-tidy-imports` ban (PHASE-0 §5); this plan does not introduce a new structure, it documents
the one the import-boundary gate already checks.

### Phase sequencing

Ordered by dependency (`plans/PLAN-00-OVERVIEW.md` §4), not by importance. Under deadline the
build order deviates from numeric order to front-load required deliverables over the bonus phase:

```
P0 Foundation → P1 Inventory → P2 MCP → P3 Agent → P5 Reasoning → P6 Generative UI →
P7 MCP Apps → P8 Commerce → P11 Delivery → P9 Observability (bonus) → P4 Memory → P10 Trust
```

P4 (Memory) and P10 (Trust) backfill after the required path is green because their `[MVP]` slice
is thin (typed `RequirementProfile` persistence, already exercised by P3's restart-resume gate;
and structured-field scoring, already true by construction from P5) — their remaining criteria are
mostly `[SCALE]`.

## Complexity Tracking

*No entries — the Constitution Check above found no violations requiring justification.*
