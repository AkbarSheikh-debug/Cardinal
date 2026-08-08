# PLAN-01 — V2 Roadmap (post-hackathon)

Six new phases, numbered `P12`–`P17`, continuing on from the twelve in `PLAN-00-OVERVIEW.md`. This
doc is the *what/how* companion to [`docs/PROPOSAL-DEALER-ECOSYSTEM.md`](../docs/PROPOSAL-DEALER-ECOSYSTEM.md),
which is the *why* — read that first if the business case for any of these isn't obvious here.

None of this is hackathon-critical. `P0`–`P11` ship first, gates green, demo rehearsed. This is what
comes after, sequenced in the order agreed below.

---

## 0. Decisions made this session

Two open questions from the proposal doc got settled, and they shape everything below:

1. **Dealer directory data is synthetic, not scraped — for the demo and for the hackathon, full
   stop.** Scraping a real "Find a Dealer" page and swapping in fake names/phone numbers still means
   the *request* to that site happened without a ToS check, and relabelled real-dealer structure with
   fictional contact details risks reading as impersonation of a real business if anyone looks
   closely. Instead: extend Phase 1's proven pattern — a deterministic, seeded generator (`P14`
   below) that produces a fictional-but-structurally-realistic dealer directory, the same way
   `src/adapters/catalogue/generator.py` already produces a fictional-but-realistic car catalogue. A
   real scraper is `[SCALE]`, gated on legal review, and never touches an OEM-branded page without
   someone on the team who owns that relationship signing off first.
2. **Voice (ElevenLabs TTS + Whisper STT) is roadmap, not demo.** The hackathon demo stays
   text + A2UI, which is already the ambitious path (subagents, MCP Apps, deterministic scoring,
   booking). Voice is architected as a thin I/O layer in `P12` so it drops in later without touching
   the phase machine, but it isn't rehearsed for judges.

Trade-in (`P13`) is confirmed as the first priority in this roadmap, per direct request.

---

## 1. Sequencing

| Order | Phase | Why here |
|---|---|---|
| 1 | **P13 — Trade-in** | Explicitly requested to go first. Needs only P3's phase-machine pattern and P5's valuation math, both already planned. |
| 2 | **P14 — Dealer directory** | Unlocks P15 (needs dealer identity to route leads to) and the payee-transparency idea from the proposal doc. |
| 3 | **P15 — Dealer CRM** | The highest commercial value in the whole roadmap; depends on P14 existing. |
| 4 | **P12 — Voice channel** | Additive, no dependencies on the others — slot in whenever there's a free cycle. |
| 5 | **P16 — Buyer decision tools** | Bundle of smaller wins over existing P5/P6 machinery. |
| 6 | **P17 — Saved searches & alerts** | Needs a notification-delivery decision (see P15 and P17 both) — settle that once, reuse for both. |

---

## P12 — Voice channel

**Owns:** speech in, speech out for the INTERVIEW phase. Ported in shape from the existing Interview
Agent repo's `backend/routers/voice.py` and `backend/services/stt_router.py`.

### Objective

Add a voice channel to the existing text-based interview **without changing the phase machine, the
`RequirementProfile`, or slot extraction** — voice is I/O only, sitting in front of the same text
pipe the `interviewer` subagent already consumes.

### Scope

**In**
- `[SCALE]` `POST /voice/transcribe` — audio in, transcript out. Whisper via Groq by default (free,
  fast — `groq/whisper-large-v3-turbo` in the source project), OpenAI Whisper as a paid fallback.
- `[SCALE]` `POST /voice/speak` — agent text in, streamed audio out via ElevenLabs
  (`eleven_turbo_v2_5`, streaming mp3, exactly as `voice.py`'s `/speak` endpoint already does it).
- `[SCALE]` `DEMO_MODE` canned transcripts, mirroring the source project's `DEMO_TRANSCRIPTS` cycling
  array and Cardinal's own existing `DEMO_MODE` philosophy (`PHASE-3-AGENT.md` §7) — same pattern,
  just for the voice endpoints.
- `[SCALE]` Browser mic capture + audio playback in `web/`.

**Out — deliberately not ported**
- The source project's multi-provider **LLM** router (`services/llm_router.py`, dispatching chat to
  OpenAI/Gemini/Groq/OpenRouter). That solves "let the user pick their model" for a different
  product. Cardinal's reasoning stays on the Claude Agent SDK — Opus 5 for orchestration, Haiku 4.5
  for extraction — per `PLAN-00-OVERVIEW.md` §6.7. Voice is a transport concern; it doesn't change
  who does the thinking.
- The source project's anxiety-detection heuristic (WPM + disfluency keywords in `voice.py`). That's
  interview-specific (calming a nervous job candidate); nothing in Cardinal's flow needs it.

### Credentials

Env var names only — **no key values were copied from the other project**, and none should be.
Secrets stay scoped per-repo; pull fresh keys from each provider's own dashboard into Cardinal's own
`.env` (gitignored, same as every other credential in this project) rather than reusing another
project's:

| Variable | Purpose | Where to get one |
|---|---|---|
| `ELEVENLABS_API_KEY` | TTS | elevenlabs.io account |
| `ELEVENLABS_VOICE_ID` | Voice selection (has a working default in the source project) | elevenlabs.io voice library |
| `GROQ_API_KEY` | Whisper STT, default path — free tier, fast | console.groq.com |
| `OPENAI_API_KEY` | Whisper STT, fallback path (paid) | platform.openai.com |

These land in whatever settings module P2/P3 end up using (a `pydantic_settings.BaseSettings`
reading `.env`, the same shape the source project's `backend/config.py` already uses) — not created
now, since P2/P3 haven't been built yet and settings should land with the code that needs them.

### Dependencies

P3 (the interview turn loop this attaches to).

### Gate sketch

| # | Criterion |
|---|---|
| 12.1 | `DEMO_MODE=true` completes voice turns from canned transcripts with no API keys present (same discipline as gate 3.3) |
| 12.2 | A mid-interview mic dropout falls back to text input without losing turn or phase state |
| 12.3 | An ElevenLabs failure (e.g. quota exhausted) degrades to text-only response — never blocks the turn |

### Risks

ElevenLabs free-tier quota exhaustion is a real failure mode the source project already handles
(`voice.py`'s `/speak` explicitly checks for `payment_required`/`paid_plan` in the error body and
tries a fallback voice ID before giving up) — port that handling, don't rebuild it from scratch.

---

## P13 — Trade-in ("Sell your current car")

**Owns:** a second conversational flow — appraising a car the customer already owns — distinct from
the buy/rent interview P3 owns.

### Objective

The fields originally proposed (mileage, model, year, fuel grade, registration year/state, ownership
count, color, modifications, expected price, and — optionally — a competing offer from elsewhere)
only make sense for a car the customer owns, not one they want. Building this as a second flow
rather than extra fields bolted onto P3's interview keeps `RequirementProfile` (typed for *wanting* a
car) from being overloaded with fields typed for *owning* one.

### Scope

- New domain model, `VehicleAppraisalProfile`: `brand`, `model`, `variant`, `year`, `mileage_km`,
  `fuel_type` (reuse `FuelType` from `src/domain/enums.py` — no new enum needed),
  `registration_year`, `registration_state`, `ownership_count`, `color`, `modifications` (free text,
  treated as **untrusted input**, the same discipline `Listing.description` already gets per
  `CONSTITUTION` I.4 — never an input to a computed valuation, display-only), `expected_price`,
  `competing_offer` (optional: amount + source — stays skippable, per the original ask, and per
  `PHASE-10`'s data-minimisation stance: ask for the minimum needed, not everything useful).
- A new subagent, `appraiser`, mirroring `interviewer`'s shape (conversation only, no tools) rather
  than overloading `interviewer` with a second job — `PHASE-3-AGENT.md` §4 is explicit that short,
  single-purpose subagent prompts are the reference shape.
- A valuation estimate, computed the same way P5 computes `market_value` and `residual_value` for
  listings (depreciation curve × mileage factor, `DECISIONS.md` D-003's clamp-at-list-price logic
  applies here too) — reused, not reinvented.
- The resulting appraisal becomes an optional credit inside checkout (P8) — "trade this in for €X
  off" — once P8 exists to attach it to.

### Dependencies

P3 (phase-machine shape to copy), P5 (valuation math to reuse), P1 (enums).

### Gate sketch

| # | Criterion |
|---|---|
| 13.1 | A scripted appraisal session reaches a complete `VehicleAppraisalProfile` within its own turn budget |
| 13.2 | Skipping the competing-offer question doesn't block flow completion |
| 13.3 | The same appraisal inputs produce the same estimate twice (same "code computes" discipline as P5's scorer) |

---

## P14 — Dealer directory

**Owns:** a `Dealer` entity so every listing resolves to a real, presentable dealer — name, address,
phone, marketplace profile — instead of a bare adapter-name string.

### Objective

`Listing.source` today is an adapter identifier (`"mock_autobazaar"`), not a dealer a buyer can
picture or call (`src/domain/listing.py:108`). This phase adds the entity that #4 and #5 of the
proposal doc both need, and that P15 (lead routing) and the payee-transparency idea both attach to.

### Scope

- New domain model, `Dealer`: `id`, `legal_name`, `display_name`, `address`, `phone`,
  `marketplace_profile_url`, `verification_status`.
- `dealer_id` foreign key on `Listing`.
- **Demo/hackathon data source: a deterministic synthetic generator**, extending
  `src/adapters/catalogue/generator.py`'s pattern — seeded, reproducible (same byte-identical-reseed
  discipline as gate 1.6), fictional names that don't collide with real, identifiable dealerships or
  brands (a simple denylist check against common real dealer/brand strings is enough to catch
  accidental collisions).
- Surfaced in the A2UI recommendation card (P6) and the booking form (P7/P8).

### `[SCALE]` — real scraper, explicitly deferred

A live scraper against a real dealer-locator page, behind a feature flag, same shape as any other
`MarketplaceAdapter` (`PLAN-00` §6.4: *"connect a real marketplace is a new file, not a rewrite"*).
Gated on:
1. A ToS/`robots.txt` check of the specific target site — done by whoever owns that check, before
   any scraping code is written. OEM-branded dealer-locator pages get extra scrutiny.
2. **Weekly** crawl cadence by default (dealer closures/staff changes are weekly-or-slower events;
   daily crawling is unnecessary load on someone else's site), with a manual override to mark a known
   closure immediately.

This is not built for the hackathon. The synthetic generator is not a placeholder for this — it's
the permanent demo/dev data source; the scraper is a separate, later, real-marketplace adapter.

### Dependencies

P1 (generator pattern), P6 (surfacing it), P8 (payee identity, once that idea gets scoped).

### Gate sketch

| # | Criterion |
|---|---|
| 14.1 | Every listing resolves to exactly one `Dealer` |
| 14.2 | Two seed runs of the dealer generator are byte-identical (same discipline as gate 1.6) |
| 14.3 | No generated dealer name matches an entry in the real-dealer/brand denylist |

---

## P15 — Dealer CRM (lead scoring + dashboard)

**Owns:** the dealer-facing side of the product — turning a completed interview into a routed,
tiered lead a real salesperson acts on. This merges the proposal doc's "purchase-intent tiering"
idea with the newly requested "dealer CRM dashboard with lead analytics" — one audience, one phase.

### Objective

This is the highest commercial-value item in the whole roadmap: the difference between a
recommendation engine and a lead-gen product a dealership pays a subscription for.

### Scope

- New domain model, `LeadScore`: `tier` (`high` / `medium` / `low`), plus the **named, logged
  signals** behind the tier — never an unexplained model judgement. The explicit timeline the buyer
  states during the interview is the primary signal; secondary behavioural signals (return sessions,
  engagement with financing detail) can adjust it, but each one is a field on `LeadScore`, not a
  hidden weight — same `FieldRef`-behind-every-claim discipline `PLAN-00` §6.2 already holds listing
  rank to. A dealer who can't see *why* a lead is High stops trusting the tier within a week.
- Tier → SLA mapping:

  | Tier | Signal | Dealer action |
  |---|---|---|
  | High | Buying in 2-3 days | Call immediately |
  | Medium | Buying in 1-2 weeks | Call within 1-2 days |
  | Low | Buying in 3-6 months, information-gathering | Call within 2-3 days, or per the dealer's own cadence |

- **Notification is in-app dashboard only for v1** — a new dealer-facing route in `web/` (separate
  auth from the buyer-facing chat) showing incoming leads sorted by tier, each with the buyer's
  `RequirementProfile` summary and an SLA countdown, plus basic analytics (lead volume by tier over
  time; conversion tracking is a later addition once there's booking data to track it against). No
  email/SMS integration for v1 — that would add a notification-service dependency the stack doesn't
  have yet, and the in-app dashboard alone answers the actual requirement ("the dealer should know").

### Dependencies

P3 (the timeline signal lives in `RequirementProfile`), P4 (behavioural signals, if used), P14
(dealer identity to route the lead to).

### Gate sketch

| # | Criterion |
|---|---|
| 15.1 | Every completed interview produces exactly one `LeadScore`, tier traceable to named signals |
| 15.2 | Tier assignment is deterministic given the same signals |
| 15.3 | A new lead appears on the dealer dashboard within one poll/push cycle of interview completion |

### Open question

**Dealer auth model** — per-salesperson login, or one shared account per dealership? This changes
the dashboard's shape and isn't answered here; needs a decision before detailed design.

---

## P16 — Buyer decision tools (bundle)

**Owns:** the smaller comparison/decision features that extend existing P5 (reasoning) and P6
(generative UI) rather than needing new subsystems. Bundled because none of them justify a phase on
their own.

| Feature | What it actually needs |
|---|---|
| **Financing & EMI comparison** | A loan calculator (`price_buy` × term × rate) as one more line in the TCO breakdown P5 already computes — not a new engine. |
| **Insurance quotes** | `Listing.insurance_band` already exists (`src/domain/listing.py:150`) but nothing computes a quote from it yet. Add a `quote` function shaped like the existing rental `Quote` in `src/domain/tco.py`. |
| **Test-drive scheduling** | Reuses P7/P8's MCP App + booking-lifecycle pattern for a lower-stakes booking (a viewing, not a purchase) — same "human confirms, code owns state" discipline, cheaper gate. |
| **Warranty comparison** | Mostly a P6 rendering job once warranty terms exist as data on `Listing`/`Dealer` — no new computation. |
| **Vehicle comparison (≤3 side by side)** | A fourth semantic rendering tool, `render_comparison`, added to P6's fixed catalog alongside the three that already exist (`render_progress`/`render_results`/`render_detail`, `PLAN-00` §6.1). |

### Held out, separately — Service history verification

**Not scoped in detail here** because it isn't an engineering decision, it's a data-sourcing one:
self-reported by the seller (cheap, unverified) vs. a paid third-party vehicle-history API
(verified, costs money per lookup). Pick the source before scoping the feature — building the UI
around self-reported data and then swapping in a paid API later is not a small change.

### Dependencies

P5, P6, P7/P8 (test-drive only).

### Gate sketch

Not written as one gate — each bullet gets its own criteria once it's prioritised out of the bundle.

---

## P17 — Saved searches & price alerts

**Owns:** persisting a buyer's search criteria across sessions and notifying them when a match
appears or a price drops.

### Why this is its own phase, not a P16 bullet

It needs two things nothing else on this list needs: **durable cross-session state beyond P4's
memory tiers** (a standing query the system re-runs, not a past preference it recalls) and an
**outbound notification channel**, which doesn't exist anywhere in the current architecture. Both are
real infrastructure additions, not extensions of existing machinery.

### Scope

- A `SavedSearch` record (the filter criteria + a per-user identity) persisted independently of a
  single session — extends P4's memory tiers rather than duplicating them.
- A scheduled or event-driven match check against new/updated listings.
- Outbound notification — email at minimum. **This decision is shared with P15**: settle the
  notification-delivery question once (transactional email provider, at minimum) and reuse the
  answer for both phases rather than picking separately.

### Dependencies

P4 (memory tiers to extend), a notification-delivery decision (shared with P15).

### Gate sketch

| # | Criterion |
|---|---|
| 17.1 | A saved search survives session restart |
| 17.2 | A new matching listing triggers exactly one notification (idempotent — no re-notify on repeat polls) |
| 17.3 | A price drop on an already-alerted listing doesn't re-trigger inside a cooldown window |

---

## What this doc is not

This is a roadmap, not a committed plan — no `[MVP]`/`[SCALE]` split against a deadline (there isn't
one for this phase of work yet), no gate scripts, no `PROGRESS.md` entries until something here
actually gets built. When work on any of `P12`–`P17` starts for real, treat it exactly like `P0`–`P11`:
one phase at a time, a real gate before it's called done, decisions worth remembering go in
`DECISIONS.md`.
