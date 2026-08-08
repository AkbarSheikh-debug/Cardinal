# Proposal — Dealer Ecosystem & Trust Layer

**Status:** Draft for team discussion — not yet a committed phase.
**Author:** Akbar, 2026-08-08. Compiled from a working session with Claude Code, grounded against
the current codebase (`PROGRESS.md`, `plans/PLAN-00-OVERVIEW.md`, `plans/PHASE-3-AGENT.md`,
`src/domain/listing.py`).
**Purpose:** Capture the business-side extensions to Cardinal — the "dealer ecosystem" the
hackathon MVP doesn't need but the real product does — so the team can scope them into phases or
a v2 plan.

---

## TL;DR

Eight ideas came out of this session. None of them break the architecture — the adapter model,
the deterministic scorer, and the "code decides, model explains" trust story all have room for
this. Two are essentially free (they reuse structure that already exists); two are new scope that
should get their own plan doc before code; one (web scraping a competitor's dealer directory)
needs a legal look before anyone builds it.

| # | Idea | Verdict | Effort vs. what exists |
|---|---|---|---|
| 1 | Cross-sell within budget | **Strong — build this** | Small. Extends a branch P3/P5 already plan. |
| 2 | Rental / new / pre-owned as explicit filters | **Good, partially done** | Small. `offer_type` exists; "new vs. pre-owned" doesn't. |
| 3 | Trade-in valuation interview | **Good idea, wrong label** | Medium-large. This is a *new flow*, not new interview fields. |
| 4 | Dealer attribution on every listing | **Strong — build this** | Small-medium. `source` exists as a string; no dealer profile object does. |
| 5 | Dealer directory + scraper | **Good instinct, needs a legal check** | Large. New data pipeline, new adapter type. |
| 6 | Corporate vs. individual customer | **Strong — build this** | Small. One new field + a routing rule. |
| 7 | Purchase-intent tiering (High/Medium/Low) | **Strong, this is the product's real moat** | Medium. New domain concept: dealer-facing leads. |
| 8 | Payee transparency before payment | **Strong — already half-promised by the constitution** | Small-medium. Extends P8/P10, doesn't fight them. |

The two that matter most commercially are **#7 (intent tiering)** and **#8 (payee transparency)** —
they're the difference between "a chatbot that shows listings" and "a system a dealership pays for
because it delivers qualified leads it can trust." Everything else supports those two.

---

## 1. Cross-sell within budget

**The idea:** the requested car (brand/model) isn't available, but the same dealer has something
else at the same budget and similar spec. Offer it instead of a dead end.

**Why it's good:** this isn't a bolt-on — it's the natural extension of a branch that's already
planned. `PHASE-3-AGENT.md` §3 defines the RESEARCH exit predicate as *"≥1 candidate survives hard
filters, **or infeasibility detected → counterfactual branch (P5)**."* Cross-sell is that
counterfactual branch, scoped specifically to "same dealer, same budget, relaxed brand/model."
The product thesis (`PLAN-00` §1) is explicitly "advisor, not filter" — refusing to return nothing
is the whole point.

**What it needs that doesn't exist yet:** nothing structural. The scorer (P5) already ranks by
fit-to-requirements; cross-sell is a second `search_cars` call with the brand/model constraint
dropped and everything else held, then explained as "this isn't the Swift you asked for, but it's
€400 under budget from the same dealer and scores 8.7/10 against what you told me matters."

**Recommendation:** fold into P5's counterfactual branch. No new phase needed.

---

## 2. Explicit rental / new / pre-owned columns

**Where this already stands:** `Listing.offer_type` already distinguishes buyable vs. rentable
(`OfferType` in `src/domain/enums.py`), and `PHASE-1-INVENTORY.md`'s gate already requires both
present with ≥40 each. So "rental vs. buy" is not a gap.

**What's actually missing:** **condition** — new vs. pre-owned (used) — is not a field on
`Listing` today. That's a real gap for a dealer-facing product: a dealer selling new stock and a
private-party used listing are different trust levels, different financing paths, and usually
different TCO math (new cars carry manufacturer warranty; the depreciation curve in `DECISIONS.md`
D-003 already assumes new-car retention at year zero, which quietly assumes "new" — worth checking
that assumption doesn't silently break once used listings without that assumption exist).

**Recommendation:** add a `condition: Literal["new", "used", "certified_pre_owned"]` enum to
`Listing`, surfaced as a first-class filter next to `offer_type` in `PHASE-1 §5`'s search filters.
Small, contained change — one enum, one filter, one gate assertion.

---

## 3. Richer car-detail fields in the interview

The requested fields — kilometers run, model, year, fuel grade (E10/E20), registration year,
ownership count, color, registration state, special modifications, expected price, **and whether
the customer has already gotten an offer elsewhere** — are all real and all useful. But naming this
"add fields to the interview agent" undersells it: **the current interview agent only asks about
the car the buyer wants** (`PHASE-3-AGENT.md`'s `interviewer` subagent elicits requirements, it
never asks about a car the person already owns). Asking "how many kilometers has *your* car done"
and "has another dealer already made you an offer" only makes sense if the person is **trading in
or selling** a car — that's a different persona and a different flow than "help me buy."

**This is a new product surface: Sell / Trade-In.** Worth naming it that explicitly so it doesn't
get built as a silent extension of the buyer interview and confuse the phase machine's
`RequirementProfile` (which is typed for *wanting* a car, not *owning* one — `PHASE-3` §6.3).

**The "competing offer" question specifically** is standard trade-in appraisal practice — it's how
a dealer calibrates whether to counter — and it's genuinely valuable signal. It should stay
optional exactly as proposed ("if you don't want to say, that's fine") both because pressuring for
it hurts conversion and because `CONSTITUTION`'s data-minimisation stance (P10) argues for asking
for the minimum needed, not everything useful.

**Recommendation:** scope this as its own plan doc — `PLAN-XX-TRADE-IN.md` — with its own
`RequirementProfile`-equivalent (say, `VehicleAppraisalProfile`) rather than folding it into P3's
existing interview. Fields to include: brand, model, variant, year, mileage_km, fuel_type (already
domain enums — reuse them), registration_year, registration_state, ownership_count, color,
modifications (free text, treated as untrusted input per `CONSTITUTION` I.4 the same way listing
`description` is), expected_price, competing_offer (optional, amount + source).

---

## 4. Dealer attribution — which dealer has it, and where

**Why it's good:** trust and conversion both need this. A recommendation that just says "AutoBazaar
listing AB-4471" is not a dealer a buyer can picture, call, or drive to. This is also a precondition
for #7 (routing leads to the right dealer) and #8 (naming the payee before money moves).

**What exists today:** `Listing.source` is a bare adapter name (e.g. `"mock_autobazaar"`) —
identifies which *marketplace integration* fetched the row, not which *physical dealer* is selling
the car. `Listing.location` (`src/domain/listing.py:50-56`) has city/country/lat-long for the
*vehicle*, but there's no `Dealer` entity with a name, address, phone, and marketplace profile URL.

**Recommendation:** introduce a `Dealer` domain model (name, legal entity name, address, phone,
marketplace profile URL, verification status) and a `dealer_id` foreign key on `Listing`. This is
also where #6 (corporate vs. individual) and #8 (payee identity) both attach naturally — one new
entity, three features hang off it.

---

## 5. Dealer directory + scraping tool

**The instinct is right:** buyers trust a recommendation more when they can see the dealer's real
storefront, and keeping that data fresh by hand doesn't scale past a handful of dealers.

**Two things to settle before building it:**

1. **Legal/ToS.** Scraping a third-party "Find a Dealer" page (the one you linked) is exactly the
   kind of thing that needs a five-minute check of that site's terms of service and `robots.txt`
   before any code gets written — not because it's necessarily prohibited, but because a scraper
   that gets an IP range blocked or draws a takedown notice is expensive to have found out about
   after the fact. Automaker/OEM dealer-locator pages are the most commonly protected of this
   category — worth checking that one specifically. Cross-check with whoever owns the OEM
   relationship on the team before scraping anything with a manufacturer's name in the URL.
2. **Freshness cadence.** Daily is unnecessary load on the source site for data that changes at the
   rate of "dealer closed" or "salesperson left" — both are weekly-or-slower events. **Recommend
   weekly**, with a manual override so a known closure can be marked immediately rather than waiting
   for the next crawl. This also keeps the scraper polite (lower request volume = lower risk of
   being blocked), which matters more than freshness here.

**How it fits the architecture:** this is not a special case — it's exactly what `PLAN-00` §6.4
already describes: *"`MockDriveNow` and `MockAutoBazaar` implement the same `MarketplaceAdapter`
protocol a real dealer DMS feed or rental API would... `connect a real marketplace` is a new file,
not a rewrite."* A dealer-directory scraper is a new adapter that fills the `Dealer` table from #4
rather than the `Listing` table — same protocol shape, different target model.

**Recommendation:** don't build until #4's `Dealer` model exists to write into, and don't build
before a five-minute ToS check. Otherwise this is additive, not risky, to the existing plan.

---

## 6. Corporate vs. individual customer

**Why it's good:** this is real signal a dealership already acts on — fleet/corporate buyers
typically move faster, buy in volume, and have different financing paths than individuals, and
sales teams already segment for it manually. Making the agent capture it once instead of a
salesperson asking on the phone is a genuine time saving, not just a data field for its own sake.

**Recommendation:** add `customer_type: Literal["individual", "corporate"]` to the buyer's profile,
captured early in the interview (it changes what's worth asking next — a fleet buyer's "budget" and
an individual's are different questions). Route corporate leads distinctly in #7's dealer handoff —
that's where the value actually gets realised, not in the flag alone.

---

## 7. Purchase-intent tiering (High / Medium / Low)

**This is the most commercially important idea in the list.** A recommendation engine is a nice
demo; a system that tells a dealership *"call this specific person today, they're buying this
week"* is a system a dealership pays a subscription for. It converts Cardinal from a buyer-facing
tool into a two-sided marketplace with a lead-gen revenue model — genuinely the difference between
a hackathon project and a product.

**The three-tier structure as proposed maps cleanly to an operational SLA:**

| Tier | Signal | Dealer action |
|---|---|---|
| **High** | Buying within 2-3 days | Call immediately |
| **Medium** | Buying within 1-2 weeks | Call after 1-2 days |
| **Low** | Buying in 3-6 months, information-gathering | Call within 2-3 days, or per dealer's own cadence |

**How to build it without it becoming a black box:** the codebase's core design principle —
*"the model picks the weights; code computes the score"* (`PLAN-00` §1, §6.2) — should govern this
exactly the way it governs listing rank. Don't let the model freehand a verdict of "this person
seems serious." Instead:

- The interview already elicits an explicit timeline as part of requirements gathering — that's
  the primary, structured signal, not a vibe read.
- Secondary signals (session behaviour: did they ask follow-up questions, come back for a second
  session, engage with financing details) can adjust the tier, but should be **named, logged
  features**, not an unexplained model judgement — the same `FieldRef`-behind-every-claim standard
  P5 already holds recommendations to (`PLAN-00` §6.2) should hold for "why is this lead High?" too.
  A dealer who gets a High-value lead that turns out to be a tire-kicker will stop trusting the
  tier within a week if they can't see why it was assigned.
- This produces an auditable `LeadScore` object — tier + the structured signals behind it — which
  is the same shape as the existing `ScoreBreakdown` P5 already builds for listings. Reuse the
  pattern rather than inventing a new one.

**What this needs that doesn't exist today:** a dealer-facing surface at all. Everything built so
far (`PLAN-00` §3 system shape) is buyer-facing — chat, A2UI canvas, MCP App host. Notifying a
dealer that a High-value lead just came in is a new interface (dashboard, webhook, email/SMS — pick
one for v1) to a new audience. Worth its own plan doc rather than squeezing it into an existing
phase; it's a distinct enough scope (auth for dealer accounts, a notification channel, an SLA
clock) that it deserves the same "what's `[MVP]` vs `[SCALE]`" treatment the twelve existing phases
get.

**Recommendation:** scope as a new phase (call it **DEALER-CRM** or similar) that consumes the
buyer-side `RequirementProfile` and produces `LeadScore` + dealer notification. Sequenced after the
buyer-facing MVP phases, since it has no value without them.

---

## 8. Payee transparency before payment

**Why this is already half-promised by the codebase:** `CONSTITUTION.md`'s hardest rule is *"no
booking is ever confirmed without an explicit human click"* — `confirm_booking` is deliberately
invisible to the model (`CLAUDE.md`, `PLAN-00` §1). That's a trust mechanism about *timing*
(nothing happens without a human in the loop). This idea is the trust mechanism about *identity*
(the human needs to know **who** they're clicking "confirm" to pay) — same philosophy, one step
earlier in the flow.

For a transaction the size of a car, "who exactly is this money going to" is not a nice-to-have.
Buyers are right to be cautious, and a system that doesn't proactively answer that question invites
the suspicion that it's hiding something.

**What it needs, concretely:** before the booking/checkout MCP App (`PHASE-7`) renders a payment
form, surface the payee's legal entity name, business registration status where available, and — if
built — a link to the `Dealer` verification status from #4. `PHASE-8-COMMERCE.md` already treats the
booking lifecycle, audit trail, and idempotency as real (not mocked) even though the payment
*gateway* is mocked for the hackathon (`PLAN-00` §6.5) — payee-identity display belongs in that same
"real lifecycle, mocked gateway" bucket, not deferred as a nice-to-have.

**Recommendation:** add a payee-identity block to the booking form MCP App (P7) and treat "payee
identity unverified" as a state the checkout UI visibly flags rather than silently allows — the
same spirit as the constitution's existing trust mechanisms. Natural home: P8 (booking lifecycle)
+ P10 (trust/PII), both already own adjacent ground.

---

## Cross-cutting notes for the team

**Privacy surface grows with this proposal.** Trade-in details (#3), corporate/individual status
(#6), and dealer contact info (#4, #5) all add personal or business data beyond what the buyer-only
MVP collects. `PHASE-10-TRUST.md` already owns PII handling — worth a pass over that phase once any
of #3/#6/#7 gets built, not after.

**Suggested sequencing**, roughly in order of "reuses existing structure" → "needs its own plan":

1. #2 (condition field) and #6 (customer type) — small schema additions, do these first.
2. #1 (cross-sell) — extend the counterfactual branch already planned in P3/P5.
3. #4 (`Dealer` model) — unlocks #5, #7, and #8 downstream.
4. #8 (payee transparency) — extends P7/P8/P10 once #4 exists.
5. #3 (trade-in flow) and #7 (lead tiering) — each deserves its own plan doc; #7 is the highest
   commercial value of everything here and probably deserves to go first between the two.
6. #5 (scraper) — after #4 exists and after a ToS check, not before.

**Resolved since this was first written** — see [`plans/PLAN-01-V2-ROADMAP.md`](../plans/PLAN-01-V2-ROADMAP.md)
for the concrete phase specs:

- **Trade-in (#3)** is confirmed as a post-hackathon flow, first in the v2 sequence — `P13`.
- **The dealer directory (#4/#5)** ships as a deterministic *synthetic* generator, the same pattern
  as Phase 1's mock catalogue — not a live scrape, even for the demo. A real scraper stays `[SCALE]`,
  gated on a ToS/legal check that hasn't happened yet — `P14`.
- **Lead tiering (#7) and the requested dealer CRM dashboard merge into one phase, P15** —
  notification is an in-app dashboard for v1, not email/SMS.
- **Voice (ElevenLabs + Whisper)** was added to scope this session as `P12` — roadmap only, not
  part of the hackathon demo.
- **New buyer-facing features** requested this session (financing/EMI, insurance quotes, test-drive
  scheduling, warranty comparison, vehicle comparison) bundle into `P16`; saved searches/price alerts
  get their own phase, `P17`, because they need infrastructure (cross-session standing queries, an
  outbound notification channel) nothing else on this list needs.

**Still open:**

- Dealer auth model for the CRM dashboard (`P15`) — per-salesperson or per-dealership login?
- Notification-delivery provider for `P17` (and, once decided, reusable by `P15` if that phase ever
  adds outbound notifications beyond the in-app dashboard).
- Service history verification's data source — self-reported vs. a paid third-party API. Not an
  engineering decision; held out of `P16` until the team picks one.
- Who owns the ToS/legal check on the dealer-directory scraper before any scraping code is written
  (`P14`, `[SCALE]`).

---

*This document is a proposal, not a plan doc — it hasn't gone through the same rigor as
`plans/PHASE-*.md` (no exit gate, no `[MVP]`/`[SCALE]` split yet). Treat it as the input to writing
those, not a replacement for them. The concrete phase specs now live in
[`plans/PLAN-01-V2-ROADMAP.md`](../plans/PLAN-01-V2-ROADMAP.md).*
