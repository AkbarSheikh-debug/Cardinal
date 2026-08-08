# PHASE 4 — Memory

**Owns:** everything the system remembers. Four tiers with different lifetimes, different owners,
and different failure modes.

The brief asks for "state maintained across interview, research and recommendation." That's the
working tier and it's table stakes. The other three tiers are the startup moat: a marketplace where
the second conversation is materially better than the first is a different product from one where
it isn't.

---

## 1. Objective

Four memory tiers with explicit ownership, plus consolidation, contradiction handling, drift
detection, and a real delete path.

## 2. Scope

### In
- `[MVP]` **Working state** — typed slots, confidence, provenance, durable across restart
- `[MVP]` **Decision journal** — append-only, queryable, answers "why X over Y" without re-deriving
- `[SCALE]` **Episodic** — cross-session user memory, markdown + frontmatter, `remember`/`recall`
- `[SCALE]` **Semantic** — pgvector retrieval over listings *and* over past decisions
- `[SCALE]` Consolidation job, contradiction detection, staleness sweep
- `[SCALE]` Preference-drift detection
- `[SCALE]` `forget_me` — complete, verified erasure

### Out
- Retrieval *ranking*. P5 owns scoring; P4 owns storage and recall.

---

## 3. The four tiers

| Tier | Lifetime | Owner | Failure if you get it wrong |
|---|---|---|---|
| **Working** | one session | **Code** | Model "forgets" the budget by turn 9 |
| **Episodic** | forever, per user | Agent (via tools) | No compounding value; every session starts cold |
| **Semantic** | forever, per corpus | Code | "Something sporty" matches nothing |
| **Journal** | forever, append-only | Code writes, agent reads | Agent re-derives a ranking it already did, differently |

### 3.1 Working state — code-owned, deliberately

```python
class Slot[T](BaseModel):
    value: T | None = None
    confidence: float = 0.0      # model's own certainty
    source_turn: int | None = None
    locked: bool = False         # user stated it explicitly; don't infer over it
```

`RequirementProfile` is a bag of `Slot`s. Every user turn runs the cheap extraction call
(P3 §5) which proposes slot updates; **code** decides whether to accept, because:

- A `locked` slot (explicitly stated: "under €28,000, hard limit") never gets silently widened by
  an inference from later chat
- Confidence below threshold means *ask*, don't assume — this is what makes the interview feel
  attentive rather than presumptuous
- The A2UI progress surface is a pure function of this object, so it can never disagree with reality

"The model remembers" degrades under context pressure. A typed object does not. This is the single
most load-bearing choice in the memory design.

### 3.2 Episodic — the compounding tier `[SCALE]`

One fact per file, YAML frontmatter, plus a `MEMORY.md` index — the format is lifted directly from
Claude Code's own auto-memory design, which is a proven shape and costs nothing to adopt.

```markdown
---
name: rejects-high-mileage
description: Won't consider anything over 80,000 km, stated as a hard limit
metadata: { type: constraint, user: u_4471, created: 2026-08-02, confidence: 0.95 }
---
Rejected three otherwise-strong candidates purely on odometer. Stated "I don't want
someone else's problems" when shown a 96k-km listing. Related: [[prefers-manual]].
```

Kinds: `preference`, `rejection`, `constraint`, `fact`. Written by the agent through a `remember`
tool with a schema — never free-form, because free-form memory becomes an unqueryable diary.

**Progressive disclosure**: the index (name + description) is in context; the body is read on
demand. Fifty memories cost ~600 tokens of index, not 20k of prose.

### 3.3 Semantic `[SCALE]`

pgvector, two corpora: listing descriptions (P1) and past decision rationales. The second is the
interesting one — "have I explained depreciation to this user before?" is a retrieval question, and
answering it stops the agent repeating itself across sessions.

### 3.4 Decision journal — `[MVP]`, and underrated

```
decisions(id, session_id, turn, kind, inputs_hash, weights jsonb, outcome jsonb, rationale, ts)
```

Append-only. Every ranking, every TCO computation, every constraint relaxation writes one row.

Why it's MVP and not scale: when a judge asks "why did you rank the Kona above the Niro?" eight
turns later, the agent reads the journal row instead of re-running the ranking. Re-deriving gives a
*subtly different* answer — different phrasing, sometimes a different order — and that inconsistency
is exactly what makes a demo look unreliable. The journal makes the agent's past self authoritative.

`inputs_hash` lets you detect "same question, same inputs" and serve the recorded answer verbatim.

---

## 4. Consolidation and contradiction `[SCALE]`

Memory that only grows becomes noise. Three background behaviours:

**Consolidation** — periodically, fold related memories into one. Three separate rejections of
high-mileage cars become one `constraint` with confidence 0.95 and the three as provenance.

**Contradiction** — a new memory that conflicts with an existing one doesn't overwrite it; it sets
`superseded_by` and keeps both. "Budget was €28k in August, €40k in November" is signal, not an
error, and the history is what makes drift detection possible.

**Staleness** — memories carry an implicit half-life by kind. A `constraint` decays slowly; a
`fact` about current inventory decays fast. Surface confidence-adjusted-for-age, not raw confidence.

---

## 5. Preference-drift detection `[SCALE]`

The differentiator that uses memory *for* something rather than merely storing it.

Signal: stated budget €28k; the user opens three listings over €40k and dwells on them. That's a
detectable divergence between `Slot.value` and revealed behaviour.

Response is a **question, not a silent update**: "You keep coming back to the €40k cars — is the
€28k a hard ceiling, or worth stretching if the right one shows up?" Silently widening the budget is
the creepy version and destroys trust; asking is the useful version.

Implement as a rule over the interaction log, not an LLM judgement call — thresholds are tunable and
the behaviour is explainable.

---

## 6. Erasure `[SCALE]`

`forget_me(user_id)` must remove: every `memories` row, every `decisions` row for that user's
sessions, every episodic file, every vector, and every trace in Langfuse. One call, verified by a
test that queries each store afterwards and asserts zero rows.

This is not optional for a product operating in the EU, and it's far cheaper to build now than to
retrofit across four stores later.

---

## 7. Exit gate

`scripts/gate_phase4.py`:

| # | Criterion | Tier |
|---|---|---|
| 4.1 | Profile survives process restart; every slot's `confidence` and `source_turn` intact | MVP |
| 4.2 | A `locked` slot is not modified by a later low-confidence inference | MVP |
| 4.3 | Journal answers "why rank A over B" from a recorded row — byte-identical to the original rationale, with **zero** model calls | MVP |
| 4.4 | Second session for a known user recalls ≥1 prior constraint without being told | SCALE |
| 4.5 | Contradicting memory sets `superseded_by`; both rows survive; recall returns the newer | SCALE |
| 4.6 | Memory index for 50 memories is ≤800 tokens (progressive disclosure holds) | SCALE |
| 4.7 | Drift detector fires on a scripted divergence and produces a *question*, not an update | SCALE |
| 4.8 | `forget_me` leaves zero rows across all four stores + Langfuse, asserted by query | SCALE |

Criterion 4.3's "zero model calls" is the whole point — assert it by counting calls, not by reading
the code.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Episodic memory becomes an unqueryable diary | Schema-constrained `remember` tool, four fixed kinds, no free-form writes |
| Recall pulls irrelevant memories into every turn | Index-only by default; body on demand; relevance threshold on retrieval |
| Drift detection feels invasive | It asks, never updates. Rule-based and explainable, not an LLM judgement. |
| Four stores means erasure misses one | Gate 4.8 queries every store independently. Add a store, add a gate line — enforced by a test that enumerates registered stores. |
| Journal grows unboundedly | Partition by month; `[SCALE]` archive older than 12 months to cold storage. |
