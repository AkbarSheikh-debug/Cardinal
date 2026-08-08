# Guardrails — indexed across phases

Every safety mechanism in the system, what it defends against, where it lives, and the gate that
proves it still works. Ordered by blast radius.

A guardrail without a gate line is a wish. If you add one, add its test in the same commit.

---

## Tier 1 — Structural. Cannot be bypassed by a prompt.

These don't depend on the model behaving. They're the ones that survive a jailbreak, a bad refactor,
or a model upgrade.

| Guardrail | Defends against | Mechanism | Phase | Gate |
|---|---|---|---|---|
| **`confirm_booking` invisible to the model** | Agent-initiated purchase | MCP `visibility: ["app"]` — the tool is absent from the resolved toolset | P2 §4, P8 §4 | 2.6, 8.2, 8.3 |
| **Gesture token required** | Confirmation without a real click, and a future refactor widening visibility | Server requires a token minted on a `click` with `isTrusted`, valid 30s | P8 §4 | 8.4 |
| **No payment SDK exists** | Accidental real charge | Static denylist over source, deps, both lockfiles | P8 §5, P10 §6 | 8.7, 10.3 |
| **Mock gateway base URL is a constant** | Misconfiguration pointing at a live endpoint | Compile-time constant, not config | P8 §5 | 8.7 |
| **Ranking reads structured fields, not prose** | Listing-text injection moving a rank | Scorer takes typed fields only; description is never an input | P5 §4, P10 §3 | 10.1 |
| **Layer boundaries** | Untestable agent, untestable domain | AST import scan + ruff ban, both | P0 §5 | 0.3 |
| **Idempotency keys + DB unique** | Duplicate bookings from a double-click | `UNIQUE(idempotency_key)`; app logic races, the database doesn't | P8 §6 | 8.5 |
| **A2UI client-enforced catalog** | Arbitrary markup injection into the UI | Renderer draws only registered components | P6 §3 | 6.1, 6.3 |
| **Cross-origin sandbox for MCP Apps** | Untrusted HTML reaching host context | Double iframe, distinct origin, CSP from `_meta.ui.csp` | P7 §5 | 7.1, 7.2, 7.3 |
| **View→server traffic is proxied** | Unaudited RPC, CSP bypass | All `tools/call` from a view routes through the host | P7 §5.3 | 7.6 |

---

## Tier 2 — Validating. Catch bad output before it's shown or stored.

| Guardrail | Defends against | Mechanism | Phase | Gate |
|---|---|---|---|---|
| **Groundedness validator** | Fabricated statistics in a rationale | Every number in a rationale must trace to a cited `FieldRef`; uncited → reject and regenerate | P5 §6 | 5.5 |
| **Critic pass** | Constraint violations reaching the user | Subagent re-checks top N against hard filters on full records | P5 §8 | 5.8 |
| **Hard filters remove, not penalise** | An excluded listing surfacing with a good score | Filtering happens before scoring, never as a zero weight | P5 §4 | 5.3 |
| **`compose_surface` validation** | Malformed or hostile component trees | Schema check, dangling refs, dup ids, depth cap; rejection returns to the model, never forwards | P6 §4 | 6.3, 6.4 |
| **Untrusted content wrapper** | Injection via listing descriptions | `<listing_content trust="untrusted">` + standing system rule | P10 §3 | 10.4 |
| **Slot locking** | Silent widening of an explicit constraint | `Slot.locked` — a low-confidence inference cannot overwrite a stated limit | P4 §3.1 | 4.2 |
| **Booking state machine** | Illegal transitions, silent no-ops | Exhaustive `(state, event)` validation | P8 §3 | 8.1 |
| **Adapter output validation** | Poisoned inventory from a compromised feed | Every adapter result validated against `Listing` before it enters the system | P1 §3 | 1.7 |
| **Result-size caps** | Context flooding and cost blowout | 20 summaries max, ≤200 tokens each; full record only on demand | P2 §6 | 2.4, 2.5 |

---

## Tier 3 — Determinism and reproducibility.

Not safety in the usual sense, but the difference between a system and a demo.

| Guardrail | Defends against | Mechanism | Phase | Gate |
|---|---|---|---|---|
| **Deterministic ranking** | Two identical questions, two different answers | Model picks weights, code scores; sort on `(score, listing_id)` | P5 §3 | 5.1 |
| **Decision journal** | Re-derived answers that subtly disagree with the original | Recorded rationale replayed verbatim; zero model calls | P4 §3.4 | 4.3 |
| **Fixed seed** | Golden set rotting under you | `Random(42)`; a seed change is a deliberate, reviewed event | P1 §4 | 1.6 |
| **`Money` is `Decimal`** | `€24,899.999999` in a checkout | Type rejects float construction | P0 §4 | 0.2 |
| **Surface identity stable** | Flicker, lost scroll, lost focus | `createSurface` once; then update | P6 §6 | 6.6 |
| **Prompts in files** | Invisible prompt regressions | No string literal in `src/` over 200 chars | P3 §7 | 0.7, 3.7 |

---

## Tier 4 — Privacy and isolation. `[SCALE]`

| Guardrail | Defends against | Mechanism | Phase | Gate |
|---|---|---|---|---|
| **Redact before export** | PII reaching a third-party trace store | Hook in the OTel export path, before the network call | P9 §7, P10 §4 | 9.6, 10.5 |
| **Card data never leaves the iframe** | Card numbers in logs, traces, DB | Only last-4 + outcome code cross the boundary | P8 §5 | 8.8 |
| **`forget_me` covers every store** | Incomplete erasure | One call, four stores + traces, verified by query per store | P4 §6 | 4.8 |
| **Tenant filter inside the query** | Cross-tenant leakage via vector ranking | Filter in the SQL/vector query, never post-fetch in Python | P10 §5 | 10.6 |
| **`tenant_id` in schema from day one** | An expensive migration later | Column exists while still single-tenant | P1 §6, P10 §5 | 10.6 |

---

## The three that matter most

If you only enforce three:

1. **`confirm_booking` is invisible to the model.** Everything else about trust is downstream of
   this. It's one config field, it's unbypassable, and it turns "we told the agent not to" into
   "the agent cannot."

2. **The scorer reads fields, not prose.** This makes rankings reproducible *and* makes listing-text
   injection economically pointless in one architectural decision. Prompt-based injection defence is
   an arms race; this ends it.

3. **A phase's gate is run, not read.** Every guardrail above is a claim until a script asserts it.
   The gates are what stop this document from becoming aspirational.

---

## Adding a guardrail

1. Which tier? If it can be talked around by a prompt, it's Tier 2 at best — consider whether a
   structural version exists.
2. Which phase owns it? One owner, no shared custody.
3. Write the gate criterion **first**, watch it fail, then implement.
4. Add the row here. A guardrail not in this table is one nobody will remember to keep working.
