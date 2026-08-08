# PHASE 11 — Delivery

**Owns:** getting it onto someone else's machine. Containers, deployment, CI/CD, documentation, and
the submission artifacts.

The phase most likely to be rushed and most likely to decide the outcome. A judge who can't run it
scores what they saw in the video; a judge who *can* run it scores what they experienced.

---

## 1. Objective

`git clone && docker compose up` produces a working system on a machine that has never seen this
repo — verified by running exactly that, on a clean machine, before submission.

## 2. Scope

### In
- `[MVP]` `docker compose up` — full stack, one command
- `[MVP]` Multi-stage Dockerfiles, non-root, healthchecks
- `[MVP]` `.env.example` with every variable, and `DEMO_MODE` working with none of them
- `[MVP]` README: what it is, how to run, architecture, and what's mocked
- `[MVP]` Playwright e2e covering all seven demo beats, screenshotting each
- `[MVP]` Slide deck + demo video
- `[SCALE]` Public deployment
- `[SCALE]` CI/CD with image publishing
- `[SCALE]` `docs/ARCHITECTURE.md`, ADR index, contributor guide

### Out
- Nothing. This is the last phase; anything unowned lands here, which is why it starts early.

---

## 3. Containers

```yaml
services:
  db:      # postgres:16 + pgvector, healthcheck, named volume
  api:     # multi-stage python:3.12-slim, non-root, depends_on db healthy
  booking: # booking-mcp, separate service — it must be a real HTTP origin (P7)
  web:     # vite build → nginx, serves the app and the sandbox origin
  langfuse:# optional profile
```

Details that matter:

- **`booking` is a separate service on its own hostname.** P7's sandbox requires a genuinely
  different origin; a second port on the same host is not one. Get this right in compose or the
  local build behaves differently from production in exactly the way that hides the bug.
- **Multi-stage everywhere.** `pip install` in a builder, copy the venv. Node build in a builder,
  copy `dist/`. Final images stay small enough to pull on venue wifi.
- **Non-root, read-only rootfs where possible, healthchecks on all four.**
- **Seed on first boot** via an idempotent entrypoint — a fresh clone must have 240 listings without
  a manual step.

---

## 4. Configuration

`.env.example` lists every variable with a comment. Two invariants:

- **`DEMO_MODE=true` works with no other variable set.** Full flow, zero keys. The gate asserts this
  by unsetting the environment entirely.
- **No secret has a default.** A missing key fails loudly at startup with a message naming the
  variable, never silently at the first model call in front of a judge.

---

## 5. Documentation

The README is a submission artifact, not an afterthought. Order matters — a judge reads the first
screen and decides how much attention to spend:

1. **One paragraph**: what it does and why it's different (advisor, not filter)
2. **A 30-second GIF** of the ranked-results → score-breakdown moment
3. **Run it**: three commands, including the no-API-key path
4. **Architecture**: the diagram from `PLAN-00-OVERVIEW.md` §3
5. **What's real and what's mocked** — explicit table. Being upfront that the marketplace and the
   gateway are synthetic reads as confidence; discovering it later reads as concealment.
6. **Requirement traceability** — the table from `PLAN-00-OVERVIEW.md` §5, mapping each brief
   requirement to the gate that proves it. Judges are scoring against a rubric; hand them the map.
7. Licence (including the AGPL decision from P10 §7), attribution, credits

---

## 6. Demo assets

### Video (3–4 minutes)

Follow the seven beats. Record **in `DEMO_MODE`** so it's reproducible and doesn't depend on API
latency. Show the interface preview's beats in order: interview → rent-vs-buy break-even → parallel
research → ranked results with the score breakdown opened → powertrain explainer → booking App →
mock checkout, ending on the trace.

Two moments to make sure land: **opening a score breakdown** (the auditability claim) and **the
agent being unable to press Confirm** (the trust claim).

### Deck (8–10 slides)

Problem → thesis (advisor not filter) → architecture → the three protocol layers and why they're
different → weights-vs-scoring split → memory tiers → guardrails → observability → what's next.

One slide worth including that nobody else will have: **the RPC audit log** from P7. It's concrete
evidence of spec compliance rather than a claim of it.

---

## 7. Exit gate

`scripts/gate_phase11.py` — and unlike the others, **part of this one is run by a human on a
different machine.**

| # | Criterion |
|---|---|
| 11.1 | Clean clone → `docker compose up` → all services healthy within 120s |
| 11.2 | Seed runs automatically; `/health` reports ≥100 listings |
| 11.3 | Playwright e2e walks all seven beats and screenshots each |
| 11.4 | e2e passes with **the entire environment unset except `DEMO_MODE=true`** |
| 11.5 | `booking` service resolves on a distinct hostname from `web` |
| 11.6 | Every image runs as non-root; no image exceeds 800 MB |
| 11.7 | `.env.example` covers every variable read anywhere in the codebase (scan asserts) |
| 11.8 | README's run instructions executed verbatim on a clean machine by someone who didn't write them |
| 11.9 | Deck and video present under `docs/` |
| 11.10 | `make verify` green: every gate 0–11 |
| 11.11 | Public deployment reachable and healthy (`[SCALE]`) |

11.8 is the one that actually matters. Everything else can pass while the README still assumes
something only your machine has.

---

## 8. Timeline

Start Phase 11 work **early** — the compose file lands in Phase 1, not at the end. What remains here
is deployment, docs, and assets.

Rough allocation for a fixed deadline:

| When | Focus |
|---|---|
| First 20% | P0, P1 — contracts and catalogue. Compose file exists and boots. |
| Next 35% | P2, P3, P5 — MCP, agent, reasoning. The system produces a real ranking in a terminal. |
| Next 30% | P6, P7, P8 — the three UI/transaction protocol layers. This is the hardest stretch; P7 is the single riskiest component. |
| Final 15% | P11, then P9 if time. Video, deck, README, clean-machine test. |

**Reserve the final 10% for the clean-machine test and the video, untouched.** Both always take
longer than expected, and a working system nobody can run scores like a broken one. Phases 4 and 10
backfill after the deadline for the startup path.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| "It works on my machine" | Gate 11.8 — a different person, a different machine, the README verbatim |
| Video recorded live and an API fails mid-take | Record in `DEMO_MODE`; gate 11.4 keeps that path working |
| Compose left to the end and nothing composes | Compose file lands in P1 and every phase keeps it green |
| Sandbox origin works locally, breaks deployed | Gate 11.5 asserts distinct hostnames in compose, matching production |
| Images too large to pull on venue wifi | Gate 11.6 |
| Deck and video squeezed into the last hour | They're gate criteria, not follow-ups |
