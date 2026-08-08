# PHASE 1 — Inventory

**Owns:** the marketplace domain. What a listing *is*, where listings come from, and how you search
them.

The decision that matters here isn't the mock data — it's the **adapter protocol**. Build the mock
behind the same interface a real dealer DMS feed would implement, and "connect a real marketplace"
later is a new file. Build it as a hardcoded JSON blob the agent reads directly, and it's a rewrite.

---

## 1. Objective

A seeded, queryable, two-marketplace catalogue behind an adapter protocol that a live feed can
implement without any change above it.

## 2. Scope

### In
- `[MVP]` `MarketplaceAdapter` protocol + contract test suite
- `[MVP]` `MockDriveNow` (rental) and `MockAutoBazaar` (dealer) implementations
- `[MVP]` Deterministic generator: 240 listings, 12 categories, ≥10 brands per category
- `[MVP]` Structured search (filters, sort, pagination)
- `[MVP]` Postgres schema + migrations
- `[SCALE]` pgvector semantic search over descriptions
- `[SCALE]` Freshness/TTL, staleness sweep, soft-delete for withdrawn listings
- `[SCALE]` One real adapter behind a feature flag (a public rental API or a CSV dealer feed)

### Out
- Ranking. P5 owns scoring; P1 owns *retrieval*.
- MCP exposure. P2 wraps these as tools.

---

## 3. The adapter protocol

```python
class MarketplaceAdapter(Protocol):
    name: str
    kind: Literal["rental", "dealer"]

    async def search(self, q: SearchQuery) -> SearchPage: ...
    async def get(self, source_id: str) -> Listing | None: ...
    async def availability(self, source_id: str, window: DateRange) -> Availability: ...
    async def quote(self, source_id: str, terms: QuoteTerms) -> Quote: ...
```

Four methods, chosen because they're the intersection of what every real marketplace exposes.
`quote` is separate from `get` on purpose: rental pricing depends on dates and duration, and folding
that into the listing record is the mistake that makes rental adapters impossible later.

**Every adapter normalises to `Listing` and retains `raw`.** The agent never learns which adapter a
result came from beyond `listing.source`, and nothing above `src/adapters` branches on it.

### Contract test suite

One parametrised suite runs against *every* registered adapter:

- `search` with no filters returns a non-empty page with a stable sort
- `search` honours every filter in `SearchQuery`; unknown filters raise, not silently ignore
- `get(source_id)` round-trips an ID from `search`
- `get` on an unknown ID returns `None`, never raises
- `availability` on a rental adapter returns real windows; on a dealer adapter returns `ALWAYS`
- Every returned `Listing` validates and carries non-empty `raw`
- Pagination is stable: page 1 + page 2 has no overlap and no gap

That suite is what makes a future real adapter a two-hour job instead of a two-week one.

---

## 4. The seeded catalogue

Generate, don't hand-write. `scripts/seed_marketplace.py`, `random.Random(42)`.

**12 categories** (brief requires ≥10): Hatchback, Sedan, SUV, Crossover, Coupe, Convertible,
Pickup, Van/MPV, Wagon, Electric, Luxury, Sports.

**24-brand pool**, ≥10 present in every category: Toyota, Honda, Hyundai, Kia, Ford, VW, Škoda,
Renault, Peugeot, Nissan, Mazda, Suzuki, Tata, Mahindra, MG, Volvo, Audi, BMW, Mercedes-Benz,
Jaguar, Tesla, BYD, Polestar, Porsche.

> **Brand names in our own generated dataset are fine. Outbound calls to any BMW Group endpoint are
> not.** The denylist scan in P10 enforces this; it is not a judgement call.

**240 listings**, roughly split: 130 dealer (`offer_type` `buy`), 90 rental (`rent`), 20 `both`.
Fields per `Listing` in [PHASE-0 §4](PHASE-0-FOUNDATION.md), plus the ones the reasoning layer needs
and nothing else has: `depreciation_curve` (a 5-point spline, not a flat %), `insurance_band`,
`service_interval_km`, `timing_mechanism` (`belt`/`chain`/`n-a`), `powertrain_archetype` (one of the
eight in P6 §5).

Those last four exist because P5's TCO engine and P6's `PowertrainExplainer` need them. Generating
them now costs nothing; retrofitting them across 240 rows later costs an afternoon.

### Realism rules the generator must respect

Randomly assigned fields produce a catalogue where a 2015 Dacia costs more than a 2023 Porsche, and
every ranking demo then looks broken. Constrain:

- `price` derives from `(brand_tier, category, year, mileage)` with bounded noise — never independent
- `mileage_km` correlates with `year` (≈12–18k/year, spread)
- `depreciation_curve` derives from `brand_tier` and `category` (a Toyota coupe holds value; a
  luxury saloon does not) — this is what makes the rent-vs-buy demo produce a *true* answer
- EVs get `timing_mechanism: n-a`, no service interval, different insurance banding
- `available_from` clusters realistically rather than uniformly across the year

---

## 5. Search

Two paths, both needed:

**Structured** — `SearchQuery` with `category ∈`, `brand ∈`, `price ≤`, `mileage ≤`, `year ≥`,
`offer_type`, `available_between`, `location_within_km`. Straight SQL, indexed.

**Semantic** `[SCALE]` — pgvector over a composed description string. Handles "something sporty for
weekend drives" and "practical but not boring", which structured filters cannot. Embed at seed time;
one index, one column.

**Result-size discipline starts here, not in P2.** `search` returns a `SearchPage` of *summaries*
(id, brand, model, year, price, one-line) plus a total count — never full records. The full record
comes from `get`. This is what stops 47 listings from landing in the model's context and is the
reason the agent stays cheap on long sessions.

---

## 6. Storage

Postgres, one schema, migrations via Alembic.

```
listings         (id, source, source_id, ...canonical..., raw jsonb, fetched_at, withdrawn_at)
listing_vectors  (listing_id, embedding vector(768))
sessions         (id, user_id, phase, profile jsonb, created_at, updated_at)
decisions        (id, session_id, turn, kind, inputs_hash, weights jsonb, outcome jsonb, ts)
memories         (id, user_id, kind, body, provenance jsonb, created_at, superseded_by)
bookings         (id, session_id, listing_id, state, idempotency_key, audit jsonb, ts)
```

`UNIQUE (source, source_id)` on listings — the deduplication primitive when two marketplaces list
the same vehicle. `withdrawn_at` rather than `DELETE`, so a booking that references a pulled listing
still resolves.

---

## 7. Exit gate

`scripts/gate_phase1.py` asserts and **prints the counts** — never eyeball these:

| # | Criterion |
|---|---|
| 1.1 | `≥100` listings (target 240) |
| 1.2 | `≥10` distinct categories (target 12) |
| 1.3 | `≥10` distinct brands **within every category** — printed per category |
| 1.4 | Both `rent` and `buy` offer types present, each `≥40` |
| 1.5 | Adapter contract suite passes against both adapters |
| 1.6 | Two seed runs with the same seed produce byte-identical output |
| 1.7 | Every `Listing` validates; `raw` non-empty on all rows |
| 1.8 | Price/mileage/year correlations hold: no listing is >2σ off its cohort's price band |
| 1.9 | `search` returns summaries only — no full record exceeds 200 tokens (`[MVP]` result-size cap) |
| 1.10 | `docker compose up` → `/health` returns 200 with a listing count |

Criterion 1.8 is the one people skip. Skip it and every ranking screenshot looks wrong.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Mock data looks obviously fake in the demo | The correlation rules in §4.1. Have someone who knows cars sanity-read 20 random rows. |
| Adapter protocol is wrong and a real feed doesn't fit | Design `quote` and `availability` against two *actual* public APIs' docs before freezing. Two hours, saves the rewrite. |
| pgvector adds container weight for marginal gain | `[SCALE]` — structured search alone is enough for the hackathon. Ship semantic only if P5 lands early. |
