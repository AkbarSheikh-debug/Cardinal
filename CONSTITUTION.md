# Constitution — Cardinal

Rules that do not bend. Every one is enforced by a test or a gate, not by good intentions.

If a change violates one of these, it needs a written entry in `DECISIONS.md` with the alternative
that was rejected and why — not a commit message. A rule removed without that entry is a bug.

Full index of every safety mechanism with its gate: [`plans/GUARDRAILS.md`](plans/GUARDRAILS.md).

---

## I. Safety

**I.1 — No real payment can execute.**
No payment SDK, API key, live gateway URL, or provider identifier may exist anywhere in this
repository — not in code, not in `requirements.txt`, not in a lockfile, not commented out. The mock
gateway's base URL is a compile-time constant, not configuration, so it cannot be pointed at a real
endpoint by an environment variable.
*Enforced by:* static denylist scan over source, dependencies, and both lockfiles — gates 8.7, 10.3.

**I.2 — No booking is confirmed without an explicit human click.**
The agent may prepare, pre-fill, recommend, explain, and open a checkout. It may never confirm one.
`confirm_booking` is declared `visibility: ["app"]`, so the tool is **absent from the toolset the
model receives** — there is no prompt to circumvent and no reasoning path that arrives at it.
Server-side, it additionally requires a gesture token minted on a trusted `click` event.
*Enforced by:* resolved-toolset assertion + Playwright session with zero agent-initiated calls +
token rejection test — gates 2.6, 8.2, 8.3, 8.4.

**I.3 — No BMW Group API is called.**
Brand names in our own generated dataset are fine. Outbound requests to BMW Group endpoints are not.
*Enforced by:* denylist scan — gate 10.3.

**I.4 — Third-party content is data, never instruction.**
Marketplace listing text enters the model wrapped and labelled `trust="untrusted"`. More
importantly, the scorer reads **structured fields only** — description prose is not an input to
ranking, so an injected instruction cannot move a result.
*Enforced by:* ~30-case injection corpus with zero permitted successes — gates 10.1, 10.2, 10.4.

**I.5 — The mock is honest about being a mock.**
Synthetic inventory is disclosed in the README and in any published MCP registry manifest.
Archetype 3D assets standing in for a specific vehicle are labelled "representative image."

*Revised by D-091.* This clause originally required `MOCK — NO REAL PAYMENT` to render
unconditionally and above the fold on the checkout form, and an equivalent `DEMO AUTH` banner
on `/login`. Both were removed from the running UI at the product owner's explicit request, made
and reaffirmed after being told what it would cost — gate 8.10 no longer has a banner to check,
and CONSTITUTION I.5 no longer requires one. The underlying facts did not change and are not
hidden: `POST /auth/request-otp` still returns the banner text and the demo codes in its JSON
body (gate 12.10), the checkout resource's own MCP description still reads "MOCK -- NO REAL
PAYMENT" for any client or maintainer who inspects it, and this file and `DECISIONS.md` still
say so in plain language. What changed is only that a person looking at the page no longer sees
it stated there.
*Enforced by:* gate 12.10 (API honesty) + README review in gate 11.8. Gates 8.10 and 12.2 now
assert the removal was deliberate rather than a banner that no longer exists.

---

## II. Architecture

**II.1 — `src/domain` and `src/agent` never import `fastapi`.**
`src/domain` additionally imports nothing that touches the network, a database, or the clock. The
agent must run from a plain Python script; the domain must be testable with no fixtures, no mocks,
and no event loop.
*Enforced by:* AST import scan **and** a ruff ban — both, deliberately. The lint rule catches it
while you type; the test catches it when someone adds a `# noqa`. Gate 0.3.

**II.2 — Ranking is deterministic.**
The model chooses weights; code computes scores. The same profile and the same seed produce the same
ordering, twice, forever. Candidates sort on `(score, listing_id)` — never on insertion order.
*Enforced by:* double-run byte comparison — gate 5.1.

**II.3 — Every quantitative claim is grounded.**
A rationale containing a number that does not trace to a cited listing field is rejected and
regenerated. Two retries, then degrade to prose with a visible "unverified" marker — never an
infinite loop.
*Enforced by:* validator rejects a deliberately fabricated statistic — gate 5.5.

**II.4 — A2UI output is validated server-side before it leaves.**
Anything the model produces via `compose_surface` is checked against the registered catalog: unknown
components, schema failures, dangling child references, duplicate ids, depth over 8. Rejection
returns an error to the model as a tool result. Partial or repaired output is never forwarded.
*Enforced by:* gates 6.1, 6.3, 6.4.

**II.5 — MCP App views are cross-origin and sandboxed.**
The inner iframe's origin differs from the host's, the CSP from the resource's `_meta.ui.csp` is
applied, undeclared `connect-src` targets are blocked and logged, and all view-initiated RPC is
proxied through the host so the audit log is complete.
*Enforced by:* browser-asserted origin check, CSP match, blocked-fetch test, network trace — gates
7.1, 7.2, 7.3, 7.6.

**II.6 — Marketplaces are adapters.**
Every source implements `MarketplaceAdapter` and normalises to `Listing` while retaining `raw`.
Nothing above `src/adapters` branches on which marketplace a result came from.
*Enforced by:* one contract suite parametrised over every registered adapter — gate 1.5.

**II.7 — Tool results are bounded.**
Search returns summaries, capped at 20 items and 200 tokens each. Full records come from an explicit
`get`. This is the difference between a session that stays cheap and one that compacts away the
interview by turn 12.
*Enforced by:* gates 2.4, 2.5.

---

## III. Process

**III.1 — A phase is done when its gate prints green.**
`make gate PHASE=N`, real output, pasted into `PROGRESS.md`. Never "the code looks right," never
"it worked when I tried it."

**III.2 — One phase at a time.**
Do not begin phase N+1's code with phase N's gate red. "These are related" is how three phases end
up half-finished.

**III.3 — `[MVP]` before `[SCALE]`, always.**
Under deadline, ship every `[MVP]` line in every phase and defer every `[SCALE]` line. Never the
reverse, however interesting the `[SCALE]` item is.

**III.4 — `PROGRESS.md` is the only source of truth for what exists.**
The plan docs describe intent and are deliberately not kept in sync with reality. If it isn't in the
repo, it doesn't exist.

**III.5 — Every non-obvious decision goes in `DECISIONS.md`** at the time it's made, with the
alternative that was rejected and why.

**III.6 — Prompts live in files.**
No prompt string in `src/` exceeds 200 characters. Prompts get reviewed, diffed, and versioned like
code, so a prompt regression is visible in `git log` instead of invisible.
*Enforced by:* gates 0.7, 3.7.

**III.7 — `DEMO_MODE=true` must always work.**
The complete flow — interview, research, recommend, book, mock-pay — runs with the entire
environment unset. Checked in CI, not the night before the demo.
*Enforced by:* gates 3.3, 11.4.

**III.8 — Write the gate criterion before the implementation.**
Watch it fail, then make it pass. A criterion written afterward tests what you built, not what you
meant to build.

---

## IV. Privacy

**IV.1 — Redact before export, not after.**
The redaction hook sits in the OpenTelemetry export path, before the network call, so PII never
reaches a third-party trace store rather than being deleted from it later. Redact values, keep
shapes (`email:<redacted:14>`) so traces stay debuggable.
*Enforced by:* scan of a real span export — gates 9.6, 10.5.

**IV.2 — Card data never leaves the App iframe.**
Only a last-4 and an outcome code cross the boundary. No card number appears in any log, trace,
database row, or audit entry.
*Enforced by:* gate 8.8.

**IV.3 — Memory is per-user and erasable.**
`forget_me(user_id)` removes every memory record, decision row, episodic file, vector, and trace in
one call. Adding a store means adding a gate line; the test enumerates registered stores so a new
one cannot be silently missed.
*Enforced by:* per-store query assertion — gate 4.8.

**IV.4 — Tenant filtering happens inside the query.**
Never fetch-then-filter in Python. For vector search especially, a post-filter leaks through the
*number* of results returned, not just their content.
*Enforced by:* two-tenant zero-cross-visibility test across all stores — gate 10.6.

---

## The three that matter most

If everything else were forgotten:

1. **`confirm_booking` is invisible to the model** (I.2). Turns "we told it not to" into "it
   cannot."
2. **The scorer reads fields, not prose** (I.4 + II.2). Makes rankings reproducible and injection
   economically pointless in one decision.
3. **Gates are run, not read** (III.1). Everything above is a claim until a script asserts it.
