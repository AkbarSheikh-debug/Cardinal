# Demo script

What to type into Cardinal, in what order, and what comes back. Every listing below is a real
row from the seeded catalogue at the default seed — nothing here is illustrative.

Two things to know before reading:

- **The interview needs four slots** before it will search: `goal` (buy or rent), `category`,
  `budget`, `target_date`. The prompts below fill all four in one or two turns on purpose, so
  the demo doesn't stall in Q&A.
- **Every result card carries a 3D viewer.** Cars in the 28-car list below show that actual
  car; anything else shows a body-style silhouette. See [3D models](#3d-models).

---

## The five-minute run

Type these in order. This is the path that shows interview → research → ranking → rent-vs-buy →
booking without a dead end.

### 1. Open with a complete brief

```
I need a family SUV under €30,000, something from 2020 or newer, and I want to buy it
```

Cardinal fills `goal=buy`, `category=suv`, `budget=30000`, and asks only for the date.

```
by the end of next month
```

→ **RESEARCH**, then four cards:

| # | Car | Price | Why it shows |
|---|---|---|---|
| 1 | 2024 Tata Safari | €14,250 | cheapest that clears the filter |
| 2 | 2024 MG Hector | €14,448 | |
| 3 | 2022 Ford Explorer | €18,524 | 7 seats |
| 4 | 2023 Honda CR-V | €20,878 | |

### 2. Push on the reasoning

```
why is the Ford Explorer ranked above the Honda CR-V?
```

Answers from the decision journal — a recorded row, not a fresh model call. Click any card to
expand its per-criterion score breakdown.

### 3. Flip to renting — the rent-vs-buy moment

```
actually I only need it for about three months, does renting work out cheaper?
```

→ TCO comparison with a real break-even month. This is the strongest single moment in the
demo: the number is computed by `src/domain/tco.py`, itemised, and never estimated.

### 4. Change your mind mid-flight

```
make it under €20,000 instead
```

→ backward transition to RESEARCH and a re-rank. Shows the phase machine isn't one-way.

### 5. Book

```
book the second one
```

→ booking form opens as a sandboxed MCP App. Fill it, confirm. **The confirm button is the
only thing that can complete a booking** — the model cannot see `confirm_booking` at all.

Test cards for the checkout step are in [`plans/PHASE-8-COMMERCE.md`](../plans/PHASE-8-COMMERCE.md);
the success card is `4242 4242 4242 4242`.

---

## Alternate openers

Each of these lands on a fully-covered result set. Pick whichever suits the audience.

| # | Say this | You get |
|---|---|---|
| **A** | `I need a family SUV under €30,000, 2020 or newer, to buy` | Tata Safari €14,250 · MG Hector €14,448 · Ford Explorer €18,524 · Honda CR-V €20,878 |
| **B** | `cheapest hatchback you can find, under €13,000, buying` | Suzuki Swift €4,844 · Kia Rio €4,885 · Kia Rio €5,665 · Renault Clio €5,853 |
| **C** | `first electric car, budget €25,000, want to buy` | BYD Atto 3 €12,298 · Peugeot e-208 €12,494 · Kia EV6 €15,448 · MG 4 €15,577 |
| **D** | `a sedan for commuting, under €20,000, nothing older than 2018` | Škoda Octavia €7,271 · BMW 3 Series €7,477 · Volvo S60 €8,246 · Peugeot 508 €8,277 |
| **E** | `small crossover, tight budget, €18,000 max` | Suzuki Vitara €7,548 · Toyota C-HR €7,681 · Škoda Kamiq €7,881 · Peugeot 2008 €8,646 |
| **F** | `I want to rent an SUV, up to €60 a day` | Nissan X-Trail €31/day · Tata Safari · MG Hector · Nissan X-Trail €51/day |
| **G** | `an estate car for the dog, under €30,000, 2020 or newer` | Škoda Superb Combi €13,172 · VW Passat Variant €18,793 · Renault Mégane Estate €18,924 · Jaguar XF Sportbrake €21,278 |
| **H** | `something fun to rent for a weekend, up to €140 a day` | Honda Civic Type R €64/day · VW Golf R · Jaguar F-Type R · Nissan GT-R €92/day |

Results are sorted price-ascending by default, which is why the cheapest car leads every list.

### Things that used to break, and now don't

Worth trying deliberately — these are the edges:

```
rent it and i need it in 2 days
```

Relative dates resolve against the current date. This exact phrasing used to return
*"Sorry, could you say that again?"* — the model had no idea what today was, so it deliberated
about placeholder dates until it ran out of tokens mid-thought (D-058).

```
I need a Lamborghini for €5,000
```

Returns an honest "nothing matches" rather than inventing a listing.

---

## 3D models

### How resolution works

Every card resolves through three tiers, most specific first
(`src/mcp/ui/vehicle_models.py`):

1. `web/public/models/vehicles/<slug>.glb` — that actual car, for the 28 below
2. `web/public/models/silhouettes/<category>.glb` — its body style, for everything else
3. `web/public/models/powertrain/<archetype>.glb` — the engine cutaway, on the detail surface

There is no "no model" case. An unsourced car degrades to a silhouette; it never renders an
empty box.

### Adding a car

Two steps, no code change:

1. Drop `<slug>.glb` and `<slug>.png` (a poster still) into `web/public/models/vehicles/`
2. Add the slug to `VEHICLE_SLUGS` in `src/mcp/ui/vehicle_models.py`

Then check your work:

```bash
python -m scripts.check_vehicle_assets
```

**Slug format** is `<brand>-<model>`, lowercased, accents folded, non-alphanumerics collapsed
to `-`: `Škoda Octavia` → `skoda-octavia`, `VW ID.4` → `vw-id-4`, `Mercedes-Benz C-Class` →
`mercedes-benz-c-class`.

### Budget — read this before downloading anything

Gate 6.7 caps **every model at 2 MB and the whole bundle at 16 MB.** A typical Sketchfab car
is 10–40 MB, so the raw download will not fit — 28 of them would be roughly 700 MB against a
16 MB budget.

Every model needs decimating and Draco-compressing before it goes in. `gltf-transform` does
both:

```bash
npm install -g @gltf-transform/cli
gltf-transform optimize raw.glb vehicles/toyota-c-hr.glb --texture-size 1024 --compress draco
```

Aim for ≤500 KB each, which leaves headroom under the 16 MB cap for all 28 plus the existing
silhouettes and powertrain assets. `scripts/check_vehicle_assets.py` fails the build if you go
over either limit.

Sources worth trying, licence permitting: Sketchfab (filter to CC-BY / downloadable),
Poly Pizza, Quaternius, and the Khronos glTF sample models. **Check the licence on each** —
several require attribution, and manufacturer-branded models are frequently uploaded without
rights. CONSTITUTION I.3 forbids serving manufacturer imagery.

### The 28 cars

These are exactly the cars openers A–H put on screen. Source all of them and every card in a
scripted run shows the real vehicle. Price ranges are the actual spread across that model's
listings in the seeded catalogue.

| # | Car | Save as | Category | Buy (EUR) | Rent (EUR/day) | Opener |
|---|---|---|---|---|---|---|
| 1 | Suzuki Swift | `suzuki-swift.glb` | hatchback | 4,844 – 7,945 | — | B |
| 2 | Kia Rio | `kia-rio.glb` | hatchback | 4,885 – 5,665 | — | B |
| 3 | Renault Clio | `renault-clio.glb` | hatchback | 5,853 – 16,100 | — | B |
| 4 | Suzuki Vitara | `suzuki-vitara.glb` | crossover | 7,548 – 14,581 | — | E |
| 5 | Toyota C-HR | `toyota-c-hr.glb` | crossover | 7,681 – 20,810 | 36 | E |
| 6 | Škoda Kamiq | `skoda-kamiq.glb` | crossover | 7,881 – 25,793 | — | E |
| 7 | Peugeot 2008 | `peugeot-2008.glb` | crossover | 8,646 | 43 | E |
| 8 | Škoda Octavia | `skoda-octavia.glb` | sedan | 7,271 – 11,239 | 61 | D |
| 9 | BMW 3 Series | `bmw-3-series.glb` | sedan | 7,477 | 39 | D |
| 10 | Volvo S60 | `volvo-s60.glb` | sedan | 8,246 | 47 | D |
| 11 | Peugeot 508 | `peugeot-508.glb` | sedan | 8,277 | — | D |
| 12 | Nissan X-Trail | `nissan-x-trail.glb` | suv | 10,330 | 31 – 51 | F |
| 13 | Tata Safari | `tata-safari.glb` | suv | 14,250 | 41 | A, F |
| 14 | MG Hector | `mg-hector.glb` | suv | 14,448 | 41 | A, F |
| 15 | Ford Explorer | `ford-explorer.glb` | suv | 18,524 | — | A |
| 16 | Honda CR-V | `honda-cr-v.glb` | suv | 20,878 | — | A |
| 17 | BYD Atto 3 | `byd-atto-3.glb` | electric | 12,298 | — | C |
| 18 | Peugeot e-208 | `peugeot-e-208.glb` | electric | 12,494 – 26,976 | — | C |
| 19 | Kia EV6 | `kia-ev6.glb` | electric | 15,448 | — | C |
| 20 | MG 4 | `mg-4.glb` | electric | 15,577 | — | C |
| 21 | Škoda Superb Combi | `skoda-superb-combi.glb` | wagon | 13,172 | 36 | G |
| 22 | VW Passat Variant | `vw-passat-variant.glb` | wagon | 18,793 | 44 | G |
| 23 | Renault Mégane Estate | `renault-megane-estate.glb` | wagon | 18,924 | 49 – 50 | G |
| 24 | Jaguar XF Sportbrake | `jaguar-xf-sportbrake.glb` | wagon | 21,278 – 35,997 | — | G |
| 25 | Honda Civic Type R | `honda-civic-type-r.glb` | sports | — | 64 | H |
| 26 | VW Golf R | `vw-golf-r.glb` | sports | 39,919 – 40,610 | 81 | H |
| 27 | Jaguar F-Type R | `jaguar-f-type-r.glb` | sports | 41,352 – 100,415 | 78 | H |
| 28 | Nissan GT-R | `nissan-gt-r.glb` | sports | — | 92 – 111 | H |

Each also needs a `.png` poster of the same name — `<model-viewer>` shows it while the GLB
streams, and gate 6.8 requires one. A single rendered still is fine.

**Sourcing note.** Numbers 13 and 14 (Tata Safari, MG Hector) are Indian-market cars with very
little free 3D availability. If you can't find them, either drop the `min_year=2020` from
opener A — which surfaces the Nissan X-Trail instead — or accept a silhouette on those two
cards. Everything else on this list is well represented in the usual libraries.

Off the scripted path, these 28 cover about 23% of the 240 seeded listings; the rest fall back
to silhouettes. Widening coverage is purely additive.

### Replace the placeholder silhouettes

The twelve body-style GLBs currently in `web/public/models/silhouettes/` are **coloured cubes**,
generated by `scripts/generate_silhouette_assets.py`. They prove the pipeline; they are not
silhouettes. Twelve generic body shapes — one hatchback, one sedan, one SUV, and so on — would
do more for how the demo looks than any single per-car model, because they cover every card
that isn't in the 28 above.

---

## Which model runs the interview

The interview runs on Qwen 3.6 (Groq) by default and the UI names no model at all. To change it:

```bash
CARDINAL_INTERVIEW_MODEL=claude        # whole session on the Claude Agent SDK
CARDINAL_SHOW_MODEL_PICKER=true        # restore the developer picker
```

Search, ranking, and booking always run on Claude regardless — the interview is the only phase
this setting touches.
