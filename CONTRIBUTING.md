# Contributing

## Read these first, in this order

1. **[`PROGRESS.md`](PROGRESS.md)** — the only source of truth for what actually exists. The plan
   docs describe *intent* and are deliberately not kept in sync with it. If it isn't in
   `PROGRESS.md`, it isn't built.
2. **[`CONSTITUTION.md`](CONSTITUTION.md)** — the hard constraints, each with the mechanism that
   enforces it. These are not style preferences; several are enforced twice on purpose.
3. **[`DECISIONS.md`](DECISIONS.md)** — the numbered *why* behind anything non-obvious. Check here
   before proposing a change that looks like an obvious improvement; it may already have been
   considered and rejected for a recorded reason.

## Setup

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # POSIX: .venv/bin/pip
cd web && npm install
```

No database is required — with `CARDINAL_DATABASE_URL` unset, the catalogue is served from memory.

## Before you open a pull request

```bash
make lint         # ruff check + ruff format --check
make typecheck    # mypy --strict src/domain; mypy over agent/adapters/api/mcp
make test         # unit + contract + integration
make verify       # all of the above plus every phase gate, chained
```

CI runs lint, typecheck, the Python test suite, and the web typecheck and build. The **phase
gates are not run in CI** — several need Playwright browsers against a live stack, and
CONSTITUTION III.1 requires their real output to be pasted into `PROGRESS.md` by a human rather
than inferred from a green check.

## The rules that bite most often

- **`src/domain`, `src/adapters` and `src/agent` never import `fastapi`.** Enforced by a ruff
  banned-api rule *and* `tests/test_layer_boundary.py` — both, deliberately: the lint rule catches
  it while you type, the test catches it when someone adds a `# noqa`.
- **No booking is ever confirmed without an explicit human click.** `confirm_booking`,
  `submit_booking_draft` and `mint_gesture_token` are declared `audience=("app",)`; the model
  cannot see they exist. This is the product's whole trust story, not a hackathon detail.
- **The model chooses weights; code computes scores.** Never move ranking arithmetic into a
  prompt.
- **Every quantitative claim carries a `FieldRef`.** A rationale with an uncited number is
  rejected and regenerated.
- **A phase's exit gate is *run*, not read, before it's called done** — `make gate PHASE=N`, real
  output, pasted into `PROGRESS.md`.

## Working on a phase

Finish one phase's gate green before starting the next one's code. Each phase doc marks its scope
`[MVP]` (hackathon-critical) or `[SCALE]` (production depth). Under deadline, ship every `[MVP]`
line and defer every `[SCALE]` line — never the reverse.

## Before you stop

- `make verify` is green, or the failure is understood and recorded rather than silently left red.
- `PROGRESS.md` reflects what actually changed.
- Anything decided along the way that isn't obvious from the code went into `DECISIONS.md` as a
  new numbered entry.

## Secrets

Never commit a `.env`. `.env.example` is the only env file in version control, and no secret in it
has a default — a missing one must fail loudly at startup rather than silently at the first model
call. Pull fresh keys from each provider's own dashboard; do not paste values from another
project.
