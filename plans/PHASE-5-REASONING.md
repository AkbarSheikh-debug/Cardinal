# PHASE 5 — Reasoning

**Owns:** the recommendation itself. Scoring, total cost of ownership, rent-vs-buy, infeasibility
handling, and the grounding rule that keeps explanations honest.

This is the product. Everything else is delivery mechanism.

---

## 1. Objective

Deterministic, auditable rankings with explanations where every claim traces to a listing field.

## 2. Scope

### In
- `[MVP]` Weighted scorer with per-criterion normalisation
- `[MVP]` `ScoreBreakdown` — the data behind the stacked contribution bar
- `[MVP]` TCO engine: purchase and rental over a user-specified horizon
- `[MVP]` Rent-vs-buy break-even solver
- `[MVP]` Explanation grounding — every claim carries a `FieldRef`
- `[MVP]` Critic pass over the top N
- `[SCALE]` Constraint relaxation / counterfactuals on infeasibility
- `[SCALE]` Calibration of weights against outcome data
- `[SCALE]` Regional tax, insurance-band, and energy-price tables

### Out
- Rendering. P6 draws the bar; P5 produces the numbers behind it.

---

## 3. The division of labour

> **The model chooses the weights. Code computes the score.**

This one sentence is the difference between a demo and a product a dealer would put their name on.

```
interviewer subagent  →  {budget_fit: 0.25, resale: 0.30, category: 0.20,
                          availability: 0.15, running_cost: 0.10}
                              │
                              ▼
domain/scoring.py     →  score = Σ wᵢ · normalise(criterionᵢ, listing)
                              │
                              ▼
explainer subagent    →  prose, with a FieldRef behind every number
```

Three properties fall out for free:

- **Reproducible.** Same profile + same seed → same order, always. Gate 5.1 runs it twice and diffs.
- **Auditable.** "Why is #2 above #3?" has a numeric answer, per criterion.
- **Testable.** `domain/scoring.py` is pure — no model, no fixtures, no event loop. Property tests
  work on it.

Ask a model to both rank and explain in prose and you get none of these. The ordering shifts between
runs, the justification is post-hoc, and there's nothing to unit-test.

---

## 4. Scoring

### Criteria

| Criterion | Normalisation | Notes |
|---|---|---|
| `budget_fit` | Piecewise: 1.0 at ≤80% of ceiling, linear decay to 0 at ceiling, hard 0 above | A hard limit is hard. Don't smooth over it. |
| `resale_strength` | Value retained at horizon / purchase price | Uses `depreciation_curve` (P1), not a flat annual % |
| `category_match` | Set overlap with stated categories, weighted by explicit vs inferred | Explicit preference outranks inferred |
| `availability` | Days between `available_from` and target date, decaying | Negative (available after the date) → hard 0 |
| `running_cost` | z-score of monthly (insurance + energy + maintenance) within the candidate set | Relative, not absolute — absolute is meaningless without a peer group |
| `condition` | Composite of mileage-for-age and service history | `[SCALE]` |
| `proximity` | Distance decay from stated location | `[SCALE]` |

**Hard filters run before scoring, not as a zero weight.** "Nothing over 80,000 km" removes rows; it
does not merely penalise them. Conflating the two is how a demo surfaces a 96k-km car with a good
score and looks broken.

### `ScoreBreakdown`

Every result carries, per criterion: the weight, the normalised value, and the product. The stacked
bar in P6 is a direct render of this — no recomputation, no possibility of the chart disagreeing
with the ranking.

---

## 5. TCO and break-even

The feature that makes the agent a decision-maker rather than a search box.

```
Buy path:     purchase + registration + insurance·h + energy·h + maintenance(h) + tax·h − resale(h)
Rent path:    (daily_rate · days(h)) + insurance_included? + energy·h + excess_mileage(h)
break_even = min h where cumulative_buy(h) < cumulative_rent(h)
```

Where `h` is the horizon in months, taken from the interview.

Details that make it correct rather than merely plausible:

- **Depreciation is a curve, not a rate.** Loss is front-loaded; a flat 15%/yr gets the six-month
  answer badly wrong, which is precisely the region where rent-vs-buy is decided.
- **Rental pricing is nonlinear.** Weekly and monthly rates aren't `daily × 7` or `× 30`. Model the
  tiers or the rent path is inflated and buy always "wins".
- **Energy cost differs by powertrain.** EV per-kWh vs petrol per-litre, with the listing's
  `efficiency` field. This is also what feeds the `PowertrainExplainer` in P6.
- **Transaction costs are real.** Registration, transfer fees, and the resale friction on the way
  out. Omitting them biases toward buying.

Output is a `TcoEstimate` with itemised lines — so the UI shows *where* the money goes, not just a
total. A single number is unpersuasive; a breakdown is an argument.

---

## 6. Explanation grounding

The rule: **every quantitative claim in a rationale carries a `FieldRef`.**

```python
RankedResult(
    rationale="Holds 53% of value at eight months — the best figure in the shortlist.",
    citations=[FieldRef("AB-4471", "depreciation_curve"),
               FieldRef("AB-4471", "price_buy")],
)
```

Enforced, not requested: a validator parses the rationale for numbers and asserts each one appears
in a cited field's value or is derivable from cited fields. A rationale with an uncited figure is
rejected and regenerated.

This costs one validation pass and eliminates the entire class of "the agent invented a statistic"
failure — which is the failure that ends a demo, because a judge *will* check one number.

`[SCALE]`: groundedness becomes a scored eval metric in P9 rather than a hard reject, once the
false-positive rate is understood.

---

## 7. Infeasibility and counterfactuals `[SCALE]`

Zero results is the ugliest path in any marketplace and the one nobody rehearses.

When hard filters eliminate everything, solve the relaxation: for each constraint, how far must it
move to admit ≥1 candidate, and how many does each relaxation admit?

> "Nothing matches all five. Raising the ceiling €2,000 opens seven. Accepting 2020 instead of 2022
> opens twelve. The mileage limit is the expensive one — relaxing it to 100,000 km opens twenty-nine,
> but every one of those needs a timing-belt service inside a year."

That's real reasoning under infeasibility, it's cheap (it's a loop over constraints), and it turns
the worst demo path into one of the best.

---

## 8. Critic pass

Before anything is shown, the `critic` subagent (P3 §4) re-checks the top N against every hard
filter and the stated budget, reading the full listing rather than the summary.

It exists because the ranking operates on normalised summaries and the occasional edge case slips —
a listing whose `available_from` is after the target date, a price that includes VAT in one source
and excludes it in another. One cheap pass catches the errors that would otherwise be the first
thing a judge notices.

---

## 9. Exit gate

`scripts/gate_phase5.py`:

| # | Criterion |
|---|---|
| 5.1 | **Determinism**: same profile + same seed, two runs, byte-identical ranking and breakdowns |
| 5.2 | `ScoreBreakdown` contributions sum to the total within 1e-9 |
| 5.3 | Hard filters remove rows — no filtered listing appears at any rank |
| 5.4 | Golden set of 20 personas: precision@3 ≥ 0.8 against expected shortlists |
| 5.5 | Groundedness validator **rejects** a deliberately fabricated statistic |
| 5.6 | TCO: break-even for a known fixture matches a hand-computed value within €50 |
| 5.7 | Rental pricing tiers applied — weekly rate ≠ daily × 7 in the output |
| 5.8 | Critic catches a seeded violation (listing available after target date) before render |
| 5.9 | `domain/scoring.py` has zero imports outside stdlib + pydantic |
| 5.10 | Counterfactual solver returns ≥2 relaxation options on a seeded zero-result query (`[SCALE]`) |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Weights the model picks are unstable across runs | Constrain to a fixed criterion set with an enum; normalise on construction; gate 5.1 catches drift |
| Golden set encodes our bias, not user value | Have two people build expected shortlists independently; disagreements are where the criteria are wrong |
| TCO looks authoritative but rests on invented constants | Every constant in one `domain/constants.py` with a source comment. Flag clearly in the UI that estimates are illustrative on synthetic data. |
| Groundedness validator over-rejects and stalls the turn | Two retries then degrade to unciteable prose with a visible "unverified" marker, never an infinite loop |
| Determinism breaks via dict ordering | Sort candidates by `(score, listing_id)` — never rely on insertion order |
