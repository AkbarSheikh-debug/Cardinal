# CLAUDE.md

Entry point for working on this repo. Router, not encyclopedia — read this, then follow a link.

## What this is

**Cardinal** — a multistep agent that interviews a buyer, researches rental and dealership
marketplaces on their behalf, and returns ranked recommendations it can defend, with booking and
payment happening inside the conversation. Built for the Amulate Summer Hackathon 2026 and designed
so the same codebase is the v0 of a real product.

Full picture: [`plans/PLAN-00-OVERVIEW.md`](plans/PLAN-00-OVERVIEW.md). Twelve phases, `PHASE-0`
through `PHASE-11`, in `plans/`.

## Where things actually stand

**Read [`PROGRESS.md`](PROGRESS.md) first, every session, before anything else.** It says which
phases have real code and which are plan-only — this file doesn't, and won't be kept in sync with
it, on purpose (one source of truth). [`DECISIONS.md`](DECISIONS.md) has the *why* behind anything
non-obvious the plan docs don't carry.

## Run it

```bash
docker compose up                      # everything: api, web, postgres+pgvector, langfuse
make dev                               # local: api on :8000, web on :5173
make test                              # unit + integration
make verify                            # lint + typecheck + test + gates 0..N, chained
make gate PHASE=5                      # one phase's exit gate
DEMO_MODE=true make dev                # full flow, zero API keys
```

## Hard constraints

Full list with enforcement mechanisms: [`CONSTITUTION.md`](CONSTITUTION.md). The three that bite
most often:

- **`src/domain` and `src/agent` never import `fastapi`.** Enforced by lint *and*
  `tests/test_layer_boundary.py` — both, deliberately.
- **No booking is ever confirmed without an explicit human click.** `confirm_booking` is declared
  `visibility: ["app"]`; the model cannot see it. This is the product's whole trust story, not a
  hackathon detail.
- **A phase's exit gate is *run*, not read, before it's called done.** `make gate PHASE=N`, real
  output, pasted into `PROGRESS.md`.

## Working on one phase at a time

Finish one phase's gate green before starting the next one's code. If a gate isn't fully scripted
yet, that's the first thing to flesh out, not the last — a criterion that exists only as prose in a
phase doc is easy to talk yourself past.

Each phase doc marks its scope `[MVP]` (hackathon-critical) or `[SCALE]` (production depth). Under
deadline, ship every `[MVP]` line and defer every `[SCALE]` line — never the reverse.

## Session end

Before stopping: `make verify` is green (or the failure is understood and recorded, not silently
left red), `PROGRESS.md` reflects what actually changed, and anything decided along the way that
isn't obvious from the code went into `DECISIONS.md`.

## More detail, only when it's relevant

- `plans/GUARDRAILS.md` — every safety mechanism, indexed across phases
- `plans/PROMPT-PATTERNS.md` — the agent role prompts and where each technique came from
- `docs/THREAT-MODEL.md` — adversary classes and what we do about each
