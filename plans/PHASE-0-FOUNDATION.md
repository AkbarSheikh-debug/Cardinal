# PHASE 0 — Foundation

**Owns:** the contracts every later phase depends on, the layering that keeps them honest, and the
CI that runs the gates.

Nothing here is visible in a demo. Everything here is why phases 1–11 don't collapse into each
other. A day spent on this saves a week of "the scorer imports the web framework and now nothing is
testable."

---

## 1. Objective

Establish domain contracts, repo layering, and a runnable verification harness — before any feature
code exists.

## 2. Scope

### In
- `[MVP]` spec-kit initialisation and the four generated artifacts
- `[MVP]` Pydantic v2 domain models (§4)
- `[MVP]` Repo layout + import-boundary enforcement
- `[MVP]` `make verify` / `make gate PHASE=N` harness
- `[MVP]` CI: ruff, mypy `--strict`, pytest, gate runner
- `[SCALE]` ADR log format and the first five ADRs
- `[SCALE]` Semantic-versioned contract package so adapters can pin a schema version

### Out
- Any business logic. Scoring lives in P5, adapters in P1.
- Database migrations. P1 owns the schema; P0 owns the *models*.

---

## 3. Repo layout

```
cardinal/
├── CLAUDE.md CONSTITUTION.md PROGRESS.md DECISIONS.md
├── plans/                       PHASE-*.md, GUARDRAILS.md, PROMPT-PATTERNS.md
├── specs/                       spec-kit output — constitution, spec, plan, tasks
├── src/
│   ├── domain/                  pure: models, scoring, tco. No I/O.
│   ├── adapters/                marketplaces, embeddings, storage
│   ├── agent/                   orchestration, subagents, prompts, memory
│   ├── mcp/                     marketplace / ui / booking servers
│   └── api/                     FastAPI. Transport only.
├── web/                         Vite + React. A2UI renderer + MCP App host.
├── prompts/                     versioned .md prompt files, never inline strings
├── scripts/gate_phase{0..11}.py
├── tests/                       unit, integration, contract, e2e
├── docs/                        THREAT-MODEL.md, ARCHITECTURE.md, deck, video
└── docker-compose.yml Makefile pyproject.toml
```

**Prompts live in files, not string literals.** They get reviewed, diffed, and versioned like code —
and a prompt regression is then visible in `git log` instead of being invisible. This is the single
cheapest process decision in the repo.

---

## 4. Domain contracts

Twelve models. Every one is `frozen=True` unless it genuinely represents mutable state.

| Model | Notes |
|---|---|
| `Listing` | Canonical vehicle record. All adapters normalise to this. Carries `source`, `source_id`, `fetched_at`, and `raw` (the untouched upstream payload) so nothing is lost in normalisation. |
| `Money` | `amount: Decimal` + `currency`. **Never a float.** Never a bare int. |
| `Slot[T]` | `value: T \| None`, `confidence: float`, `source_turn: int`, `locked: bool`. The unit of interview state. |
| `RequirementProfile` | Mutable. `goal`, `category`, `budget`, `target_date`, `horizon_months`, `use_case`, `hard_filters`. Each a `Slot`. |
| `CriterionWeight` | Named criterion + weight in `[0,1]`. Weights are normalised on construction. |
| `ScoreBreakdown` | Per-criterion `(weight, normalised_value, contribution)` + total. Reconstructs the stacked bar with no extra query. |
| `RankedResult` | `listing_id`, `rank`, `ScoreBreakdown`, `rationale`, `citations: list[FieldRef]`. |
| `FieldRef` | `(listing_id, field_name)` — the grounding primitive. Every claim in a rationale must carry one. |
| `TcoEstimate` | Line items over a horizon: purchase/rental, depreciation, insurance, energy, maintenance, tax, resale. Plus `break_even_month \| None`. |
| `BookingDraft` → `Booking` | Separate types on purpose. A draft has no ID in the bookings table; promoting one is an explicit, audited transition. |
| `MemoryRecord` | `kind` (`preference`/`rejection`/`constraint`/`fact`), body, provenance, `created_at`, `superseded_by`. |
| `DecisionEntry` | Append-only. `(session, turn, kind, inputs_hash, weights, outcome, rationale)`. |

Two rules that prevent most of the bugs this class of app has:

- **`Money` everywhere, `Decimal` inside.** Float arithmetic on prices produces `€24,899.999999` in
  a checkout screen, and it will happen on demo day.
- **`Listing.raw` is retained.** When a real adapter lands and a field turns out to be mapped
  wrong, you can re-normalise historical rows instead of re-fetching.

---

## 5. Layering enforcement

```python
# tests/test_layer_boundary.py
FORBIDDEN = {
    "src/domain":   {"fastapi", "sqlalchemy", "anthropic", "claude_agent_sdk", "httpx"},
    "src/adapters": {"fastapi", "claude_agent_sdk"},
    "src/agent":    {"fastapi"},
}
```

Walk each package's ASTs, collect every `Import`/`ImportFrom`, assert the intersection is empty.
Mirror the same rule as a ruff `flake8-tidy-imports` ban so it fails in the editor too. Both,
deliberately — the lint rule catches it while you type, the test catches it when someone adds a
`# noqa`.

`src/domain` additionally must import nothing that touches the network or the clock. A pure domain
means P5's scorer is testable with no fixtures, no mocks, and no event loop.

---

## 6. Verification harness

```make
verify: lint typecheck test gates
gate:   ## make gate PHASE=5
	python scripts/gate_phase$(PHASE).py
gates:
	@for p in $$(seq 0 11); do python scripts/gate_phase$$p.py || exit 1; done
```

Every `gate_phaseN.py` follows the same shape: print each criterion with `PASS`/`FAIL`/`PENDING`,
exit non-zero on any `FAIL`, exit 0 when everything unimplemented is `PENDING`. A phase that hasn't
started reports all-`PENDING` and passes — that's correct, not broken. It means `make verify` stays
green from day one and only turns red on a *regression*.

---

## 7. spec-kit

```bash
uvx --from git+https://github.com/github/spec-kit.git specify init cardinal
/speckit.constitution   # → seeds CONSTITUTION.md; keep ours as the source of truth
/speckit.specify        # → specs/spec.md
/speckit.plan           # → specs/plan.md
/speckit.tasks          # → specs/tasks.md
```

Commit all four. The brief requires spec-driven development; the artifacts are the evidence. Keep
`CONSTITUTION.md` at the repo root as the human-authored source of truth and let spec-kit's
constitution reference it rather than duplicate it — two constitutions that drift is worse than one.

---

## 8. Exit gate

`scripts/gate_phase0.py` asserts:

| # | Criterion |
|---|---|
| 0.1 | Every domain model imports and round-trips its fixture JSON (`model_validate` → `model_dump` → equal) |
| 0.2 | `Money` rejects `float` construction; arithmetic preserves `Decimal` |
| 0.3 | Import-boundary scan finds zero violations across all four layers |
| 0.4 | `mypy --strict src/domain` reports zero errors |
| 0.5 | `specs/` contains constitution, spec, plan, tasks; all non-empty |
| 0.6 | `make verify` runs to completion on an empty implementation (all later gates `PENDING`) |
| 0.7 | `prompts/` contains no `.py`; `src/` contains no prompt string over 200 chars (`[SCALE]`) |

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Contracts churn once real adapters land | `Listing.raw` + a schema `version` field. Additive changes only after P1 freezes. |
| `mypy --strict` on the whole tree is too slow to keep green | Strict on `src/domain` and `src/agent` only; standard elsewhere. |
| spec-kit's generated constitution drifts from ours | Ours is the source of truth; spec-kit's references it. Gate 0.5 checks the reference exists. |
