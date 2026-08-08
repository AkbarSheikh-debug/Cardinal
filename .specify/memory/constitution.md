<!--
Sync Impact Report
Version change: (none) → 1.0.0
Modified principles: n/a (initial ratification)
Added sections: Core Principles (I–V), Source of Truth, Governance
Removed sections: none
Templates requiring updates:
  - .specify/templates/plan-template.md   ✅ Constitution Check gate maps to principles I–V below
  - .specify/templates/spec-template.md   ✅ no changes required (principles are process/architecture, not feature-shape)
  - .specify/templates/tasks-template.md  ✅ no changes required
Follow-up TODOs: none
-->

# Cardinal Constitution

This file is spec-kit's governance document — the one `/speckit-plan`'s Constitution Check gate
reads. It is deliberately thin. **The full, enforced rule set lives in
[`CONSTITUTION.md`](../../CONSTITUTION.md) at the repo root**, which remains the human-authored
source of truth; this file summarizes it into the five principles spec-kit's own workflow checks
against, so the two documents can never drift into disagreement about substance — only this one
can lag on presentation.

## Core Principles

### I. Safety Is Structural, Not Prompted
No real payment can ever execute — no payment SDK, API key, or live gateway URL may exist anywhere
in the repository, not even behind a flag. Booking confirmation requires an explicit human click:
`confirm_booking` is declared `visibility: ["app"]`, so it is absent from the toolset the model
receives — there is no prompt to circumvent because there is no reasoning path that reaches it.
Third-party content (marketplace listings) is data, never instruction, and is wrapped and labelled
`trust="untrusted"` before it reaches the model. Full detail: root `CONSTITUTION.md` §I.

### II. Domain Purity & Deterministic Reasoning
`src/domain` and `src/agent` never import `fastapi`; `src/domain` additionally touches no network,
database, or clock. The model chooses scoring **weights**; code computes the **score** — the same
profile and seed produce the same ranking, twice, forever, sorted on `(score, listing_id)`, never
insertion order. Every quantitative claim in a rationale must trace to a cited listing field
(`FieldRef`); an ungrounded number is rejected and regenerated, twice, then degrades to a visibly
marked "unverified" prose claim rather than looping forever. Full detail: root `CONSTITUTION.md`
§II.1–II.3.

### III. Gates Are Run, Not Read
A phase is done when `make gate PHASE=N` prints green and its real output is pasted into
`PROGRESS.md` — never "the code looks right." Work proceeds one phase at a time; phase N+1's code
does not begin with phase N's gate red, except where a recorded, justified exception exists (see
`DECISIONS.md`). `[MVP]` scope ships before `[SCALE]` scope, always, under deadline. Every
non-obvious decision is written to `DECISIONS.md` at the time it is made, with the rejected
alternative. Full detail: root `CONSTITUTION.md` §III.

### IV. Privacy By Construction
PII is redacted before it is exported, not after — the redaction hook sits in the trace-export
path itself. Card data never leaves the payment App's iframe; only a last-4 and an outcome code
cross that boundary. Memory is per-user and erasable in one call (`forget_me`), and tenant
filtering happens inside the query, never as a post-fetch filter in Python. Full detail: root
`CONSTITUTION.md` §IV.

### V. Spec-Driven, Progress-Tracked
The brief requires spec-driven development; these four artifacts (`constitution.md`, `spec.md`,
`plan.md`, `tasks.md` under `specs/`) are the evidence, kept current as phases land — not a
one-time exercise. `PROGRESS.md` remains the **only** source of truth for what is actually built;
the `plans/PHASE-*.md` docs describe intent and are deliberately never edited to match reality. If
a capability isn't reflected in `PROGRESS.md`, it doesn't exist yet, however complete the plan doc
sounds.

## Source of Truth

Where this file and root `CONSTITUTION.md` could be read as disagreeing, root `CONSTITUTION.md`
wins — it carries the enforcement mechanism (a test or a gate) for every rule; this file is a
navigation aid, not an independent ruleset. Amending a rule here without amending it there is a
bug, not a valid state.

## Governance

**Amendment procedure.** A change to a Core Principle above requires a corresponding change (or an
explicit note that none is needed) to root `CONSTITUTION.md`, plus a `DECISIONS.md` entry naming
the alternative that was rejected and why (root `CONSTITUTION.md` III.5). A change to root
`CONSTITUTION.md` alone does not require bumping this file's version unless it changes which of the
five principles above it falls under.

**Versioning policy.** Semantic versioning on this file: MAJOR for a principle removed or
redefined in a backward-incompatible way, MINOR for a principle added or materially expanded,
PATCH for wording/clarity fixes. `/speckit-constitution` re-derives the version bump from the diff
each time it runs.

**Compliance review.** `make gate PHASE=N` and `make verify` are the review — a plan or task list
that would violate a principle above fails its phase's gate by construction (import-boundary scan,
denylist scan, determinism check, groundedness validator, etc.), not by a reviewer noticing.

**Version**: 1.0.0 | **Ratified**: 2026-08-08 | **Last Amended**: 2026-08-08
