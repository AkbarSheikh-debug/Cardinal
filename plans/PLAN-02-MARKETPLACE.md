# PLAN-02 — Marketplace (the two-sided build)

**Status:** committed build spec. This is the single document the remaining build runs from.
**Supersedes:** [`plans/PLAN-01-V2-ROADMAP.md`](PLAN-01-V2-ROADMAP.md)'s numbering (mapping in §0.6).
**Companion:** [`docs/PROPOSAL-DEALER-ECOSYSTEM.md`](../docs/PROPOSAL-DEALER-ECOSYSTEM.md) is the *why*
for most of what follows — read it if a business case here isn't obvious.

Five phases, `P12`–`P16`, that turn Cardinal from a buyer-facing advisor into a two-sided
marketplace: accounts and login, a seller identity behind every listing, a cart with a real payee
disclosure before money moves, a seller console that gets notified with a scored lead, and a voice
channel on both ends of the conversation.

Everything in `P0`–`P11` stays green throughout. Nothing here is allowed to regress a gate that
already passes — several sections below exist specifically to say *how* to add a feature without
breaking the guarantee that sits next to it.

---

## 0. Decisions taken up front

These constrain every phase below. Each one resolves a conflict that would otherwise get resolved
badly, silently, mid-build. When these land in code they get real `D-0NN` entries in `DECISIONS.md`
(CONSTITUTION III.5); they are written here first so the build doesn't have to rediscover them.

### 0.0 — The compliance boundary: what actually cannot move

Everything in this plan was checked against the Amulate brief. Exactly **four** things are
immovable. Everything else — including every feature in this document — is free design space, and
should be built the way the product wants rather than the way a cautious reading of the brief might
suggest.

| Immovable | Source | Where it's honoured here |
|---|---|---|
| Form-filling **and** payment/checkout are **MCP Apps, rendered in the chat** | "Required — MCP Apps… so booking/purchase confirmation happens without leaving the conversation" | §0.1 — both, on every route |
| Catalogues + live agent progress render via **A2UI**, "not static HTML" | Brief, Possible Functions | P13/P14/P15 extend the existing A2UI catalog, never bypass it |
| **No real payments. No BMW Group APIs.** | Brief, explicit | CONSTITUTION I.1/I.3, gates 8.7 / 10.3, unchanged |
| ≥100 listings, ≥10 categories, ≥10 brands per category | Brief, mock-marketplace option | Already exceeded (240/12/11–14); gate 13.8 keeps it green |

**Not in the brief at all**, therefore free: accounts and login, roles, a seller dashboard, a cart, a
dedicated checkout route, lead scoring, income capture, dealer identity, payee disclosure, and voice.
The brief is silent on all of it. Silence is permission — a bonus feature cannot violate a
requirement that does not exist.

Where this plan constrains one of those free items, the constraint comes from **CONSTITUTION.md**
(this repo's own rules) or from ordinary privacy sense — not from the brief. Those are ours to
trade off, and §0.3 and §P16 below now do exactly that.

### 0.1 — The checkout App renders on `/cart` **with the chat rail still mounted**

The one genuine constraint. The brief requires the payment interface to be an MCP App rendered so
confirmation happens *without leaving the conversation*. A plain `/cart` page with its own pay
button drops a mandatory requirement and bypasses every guarantee gate 8 proves — the gesture token,
`confirm_booking`'s invisibility, idempotency, the mock banner, server-side price recomputation.

You still get the full dedicated page you asked for. Three things make it compliant *and* better:

1. **`/cart` keeps the chat rail mounted alongside the cart** — same session, same SSE stream, same
   agent, still answering questions while the buyer reviews the order. The conversation is
   therefore never left, literally rather than by argument. This is a stronger demo than an overlay:
   the judge watches the buyer ask "is the insurance included?" *while* looking at the checkout.
2. **The payment surface is the existing `ui://checkout/payment` App**, mounted through the existing
   `McpAppHost` over the existing `POST /mcp-apps/{session_id}/rpc` proxy. Same resource, same
   sandboxed cross-origin iframe, same CSP, same audit log, same `mint_gesture_token` →
   `confirm_booking` sequence. Cheap, because P7 built the host route-agnostic — gate 7 already
   drives it from a page with no chat and no live session on it at all.
3. **The App's HTML is entirely yours.** `src/mcp/booking/static/checkout.html` is plain
   HTML/CSS/JS with no framework and no build step. "It's an MCP App" is a statement about the
   protocol and the trust boundary, *not* about how it looks. Make it look like any checkout page
   you want — full-width, styled to match the site, indistinguishable from a native page. Nothing
   about compliance requires it to look like an embedded widget.

**The in-chat overlay path must keep working too.** Gates 8.3, 8.6, 8.10, 8.11 and 11.3 all drive it.
`/cart` is an addition, not a migration.

> Rejected: a `/cart` page that POSTs to a new `/checkout/pay` endpoint. Simpler to write, drops a
> mandatory requirement, and silently deletes CONSTITUTION I.2 — a payment path the model can't see
> is worthless the moment a second path exists that nobody guarded.

### 0.2 — Dummy auth is loudly dummy

The OTP codes are `123456`, `234567`, `345678`, accepted for any account. That is requested and it is
fine for a hackathon — but CONSTITUTION I.5 ("the mock is honest about being a mock") applies to
authentication exactly as it applies to payment. Therefore:

- A `DEMO AUTH — ANY CODE BELOW WORKS, NOT REAL SECURITY` banner renders unconditionally and above
  the fold on the login screen, in the same spirit and roughly the same visual weight as
  `MOCK — NO REAL PAYMENT`.
- The three codes are a **compile-time constant**, not configuration — mirroring
  `MOCK_GATEWAY_BASE_URL` (CONSTITUTION I.1). No env var can turn demo auth into a claim of real
  auth, and no env var can be mistaken for a real secret.
- **No JWT, no password hashing, no auth SDK.** An opaque random token in a server-side table. A
  fake signing secret checked into a repo is the single most common way a demo app grows a real
  vulnerability, and skipping JWT entirely means there is no secret to leak and no algorithm to
  confuse. Real auth is `[SCALE]`, and its seam is the token store.

### 0.3 — Income is captured exactly, stored once, and travels only as a band

"How much they earn" was requested and the brief has nothing to say about it, so this is a design
call, not a compliance one. **Capture the exact figure.** It's the honest input for affordability
guidance and a financing pre-check, and a band alone loses real information at the boundaries
(€49k and €26k are not the same buyer).

What keeps it from becoming the most dangerous field in the system is *containment*, not
coarsening — capture precisely, then narrow at every boundary it crosses:

- `annual_income: Money | None` on `BuyerProfile` — exact, optional, buyer-entered.
- `income_band` is **derived**, never separately entered: an `IncomeBand` enum
  (`under_25k`, `25k_50k`, `50k_100k`, `100k_plus`, `undisclosed`) computed from the figure.
- **The exact figure never leaves the buyer's own account.** It is what the buyer sees on their own
  profile and what a financing calculation reads server-side. The **band** is what P15's lead
  scorer consumes; **neither** is ever shown to a seller (§P15's privacy rule); **neither** is ever
  serialised into a model prompt.
- Both are added to the OTel redaction list (CONSTITUTION IV.1) alongside email and phone —
  redacted before export, keeping shape (`annual_income:<redacted:6>`) so traces stay debuggable.
- **Optional, with `undisclosed` a first-class, non-penalised answer**, presented as such in the UI.
  The lead scorer treats it as neutral, never negative — otherwise the field becomes coercive by
  the back door and the tier starts punishing privacy.

The rule this encodes, worth stating once: precision at the point of capture, minimum viable
granularity at every boundary after it. That is a stronger privacy posture than refusing to collect
the number, and it is the one that keeps the feature.

### 0.4 — Seller notification reuses the SSE channel that already exists

`GET /sessions/{id}/events` already streams `QueueUISink` messages to the browser and is already
correctly configured in `web/nginx.conf` (unbuffered, 1h read timeout). The seller console gets
`GET /seller/{seller_id}/events` — the same `QueueUISink` pattern, a second consumer, no new
infrastructure, no message broker, no polling loop.

> Rejected: email/SMS notification. It needs a provider dependency the stack doesn't have, and
> "the seller should know" is fully answered by a live dashboard. Outbound delivery stays the open
> question `PLAN-01` §P17 already flagged.

### 0.5 — The lead tier is computed by code and explained from named signals

Exactly the discipline CONSTITUTION II.2 already imposes on listing rank, for the same reason: a
dealer who cannot see *why* a lead was scored High stops trusting the tier within a week, and an
unexplained model verdict about a real person's intent is the kind of thing that should never have
been a vibe read in the first place.

`LeadScore` carries `tier`, a numeric score, and the **named, individually-logged signals** that
produced it — the same shape as P5's `ScoreBreakdown`. Deterministic: same signals, same tier,
twice. The model may write the sentence; it never picks the tier. And the tier is always phrased as
an estimate with its reasoning attached ("High purchase intent (estimated) — target date is 3 days
out, added to cart, opened checkout"), never as an assertion about the person.

### 0.6 — Numbering

`PLAN-01`'s phase numbers are superseded. Nothing in `PROGRESS.md` referenced them as built, so this
costs nothing but needs saying once, loudly:

| This doc | Was, in PLAN-01 | Note |
|---|---|---|
| **P12 — IDENTITY** | *(new)* | Not in any prior plan |
| **P13 — DEALER** | P14 — Dealer directory | Absorbed, plus proposal #2's `condition` field |
| **P14 — CART** | *(new)*, plus proposal #8 | Payee transparency lands here |
| **P15 — SELLER CONSOLE** | P15 — Dealer CRM | Absorbed unchanged in intent |
| **P16 — VOICE** | P12 — Voice channel | Absorbed, re-sequenced last |
| P17 — Trade-in | P13 — Trade-in | Still roadmap, not built here |
| P18 — Buyer decision tools | P16 | Still roadmap, not built here |
| P19 — Saved searches & alerts | P17 | Still roadmap, not built here |

---

## 1. Sequencing

Strict order. Each phase's gate green before the next one's code (CONSTITUTION III.2).

```
P12 IDENTITY ──┬──▶ P13 DEALER ──┬──▶ P14 CART ──┬──▶ P15 SELLER CONSOLE
               │                 │               │
               │                 └───────────────┘
               │        (payee identity)   (lead routing + intent signals)
               │
               └──────────────────────────────────────▶ P16 VOICE  (independent)
```

- **P12 first** because every other phase needs to know who is acting.
- **P13 before P14** because a payee disclosure needs a payee that exists.
- **P13 before P15** because a lead has to be routed to a specific seller.
- **P14 before P15** because cart-add and checkout-opened are the two strongest intent signals the
  scorer reads.
- **P16 last** because it touches no data model and blocks nothing. If time runs out, this is the
  one to cut — and it should be cut before any `[MVP]` line above it.

---

## P12 — IDENTITY

**Owns:** accounts, the buyer/seller role split, dummy OTP login, and the profile fields collected
at signup.

### Objective

One account model, two roles, one login screen that branches. Everything downstream — which listings
are mine, which leads are mine, who the payment goes to — resolves from an account id instead of
being implicit in a browser session.

### Scope

**In**
- `[MVP]` `src/domain/identity.py` — pure pydantic, no db, no clock, no fastapi (CONSTITUTION II.1):
  - `AccountRole` StrEnum: `buyer` | `seller`
  - `CustomerType` StrEnum: `individual` | `corporate` (proposal #6)
  - `IncomeBand` StrEnum: per §0.3
  - `Account`: `id`, `role`, `email`, `full_name`, `phone`, `created_at`
  - `BuyerProfile`: `account_id`, `customer_type`, `employer` (optional, free text — **untrusted
    input**, display-only, same discipline as `Listing.description` per CONSTITUTION I.4),
    `annual_income: Money | None` (exact, optional), `income_band` (**derived** from it, never
    separately entered — §0.3), `city`, `country`
  - `SellerProfile`: `account_id`, `dealer_id` (nullable until P13 fills it), `role_title`
- `[MVP]` `DEMO_OTP_CODES: Final = ("123456", "234567", "345678")` — compile-time constant (§0.2)
- `[MVP]` `src/adapters/identity_store.py` — protocol + `InMemoryAccountStore`;
  `src/adapters/db/identity_store.py` — `PostgresAccountStore`
- `[MVP]` Migration `0003_identity.py` — `accounts`, `account_profiles`, `auth_tokens`
- `[MVP]` API in `src/api/main.py`: `POST /auth/request-otp`, `POST /auth/verify-otp`,
  `GET /auth/me`, `POST /auth/logout`
- `[MVP]` Opaque bearer token, server-side table, 24h TTL, single revocation path
- `[MVP]` `web/` router (`react-router-dom`) + `/login` route with role toggle and the demo banner
- `[MVP]` Seeded demo accounts (one buyer, one seller) so `DEMO_MODE` needs no signup
- `[SCALE]` Real OTP delivery, real sessions, password/passkey, rate limiting on OTP attempts
- `[SCALE]` Multi-tenancy (`tenant_id`) — still deferred, still gate 10.6's problem

**Out**
- Anything about *which* listings a seller owns — P13.

### Notes that will save a day

- `web/` has **no router today** — `App.tsx` is a single page. Adding one is the largest frontend
  change in this whole plan; do it as its own commit, with the existing buyer experience moved
  wholesale to `/` and provably unchanged, before any new route gets written.
- `web/nginx.conf` already has an SPA fallback (`try_files $uri $uri/ /index.html`), so client-side
  routes work in the container without change. The **API prefixes do not** — see §2.2.
- Token in an `httpOnly` cookie, not `localStorage`. It costs nothing here and it is the difference
  between a demo that models the right thing and one that models the wrong thing.

### Dependencies

P0 (domain layering, gate harness), P11 (`.env.example` coverage — gate 11.7 will fail if a new var
appears and isn't listed).

### Exit gate — `scripts/gate_phase12.py`

| # | Criterion |
|---|---|
| 12.1 | Each of the three demo OTP codes authenticates a seeded account; a fourth code is rejected |
| 12.2 | `DEMO AUTH — NOT REAL SECURITY` renders above the fold on `/login` (asserted in a browser, not from source) |
| 12.3 | Denylist scan: zero JWT libraries, zero auth-provider SDKs, zero signing secrets anywhere in source, deps, or both lockfiles (extends `scripts/gate_common.py`'s existing scan) |
| 12.4 | A buyer token cannot read any `/seller/*` route; a seller token cannot read another seller's; both return 403, not 404-by-accident |
| 12.5 | Account + profile survive process restart, every field intact (same shape as gates 3.2 / 4.1) |
| 12.6 | `annual_income`, `income_band` and `phone` are absent from every exported OTel span, and the redaction marker is present (extends gate 9.6's scan) |
| 12.7 | `annual_income`, `income_band` and `employer` appear in zero model-facing payloads — scan of everything serialised toward the SDK |
| 12.8 | `income_band` is always consistent with `annual_income` — derived, never independently settable through any route |
| 12.9 | `DEMO_MODE=true` completes a full buyer flow with no signup and no `ANTHROPIC_API_KEY` (CONSTITUTION III.7) |
| 12.10 | `[SCALE]` OTP attempt rate limiting |

---

## P13 — DEALER

**Owns:** the seller identity behind every listing. Proposal doc #4 (dealer attribution) and #2
(new / pre-owned), and the entity that P14's payee disclosure and P15's lead routing both hang off.

### Objective

`Listing.source` is `"mock_autobazaar"` — an adapter name, not a dealer a buyer can picture, call, or
drive to. This phase adds the dealer, links it to a seller account, and surfaces it everywhere a
listing is shown.

### Scope

**In**
- `[MVP]` `src/domain/dealer.py`: `Dealer` — `id`, `legal_name`, `display_name`, `address`, `city`,
  `country`, `phone`, `rating` (0–5, one decimal), `review_count`,
  `verification_status` (`verified` | `unverified` | `pending`), `marketplace_profile_url`
- `[MVP]` `dealer_id` on `Listing` and `ListingRow`; every listing resolves to exactly one dealer
- `[MVP]` `condition` on `Listing` — `new` | `used` | `certified_pre_owned` (proposal #2), as a
  first-class search filter next to `offer_type`
- `[MVP]` **Deterministic synthetic dealer generator**, extending
  `src/adapters/catalogue/generator.py`'s proven pattern — seeded, byte-identical across two runs
  (the discipline gate 1.6 already enforces for the catalogue)
- `[MVP]` Real-dealer/brand collision denylist over generated names
- `[MVP]` `PayeeIdentity` — the projection P14 renders: legal name, address, phone, verification
  status. A view model, not a second source of truth
- `[MVP]` `SellerProfile.dealer_id` populated; a seller account owns exactly one dealer's listings
- `[MVP]` Dealer surfaced on the A2UI `CarCard` — **both** catalogs (`src/mcp/ui/catalog.py` and
  `web/src/a2ui/catalog.tsx`); a prop registered on one side only fails validation on the other
- `[MVP]` Migration `0004_dealers.py`
- `[SCALE]` A real dealer-directory scraper. **Not built here.** Gated on a ToS/`robots.txt` check by
  whoever owns it, weekly cadence, and never against an OEM-branded page without sign-off. The
  synthetic generator is the permanent demo data source, not a placeholder for this.

### The `condition` field has a hidden cost — check it

`DECISIONS.md` D-003's depreciation curve assumes new-car retention at year zero. Once `used` and
`certified_pre_owned` listings exist, that assumption is silently wrong for most of the catalogue.
Either the curve becomes condition-aware or the assumption gets written down as a known
approximation — but it does not get to stay unexamined once the field that contradicts it exists.

### Dependencies

P1 (generator pattern, `ListingStore`), P6 (both catalogs), P12 (seller accounts to link).

### Exit gate — `scripts/gate_phase13.py`

| # | Criterion |
|---|---|
| 13.1 | Every listing in a fully seeded catalogue resolves to exactly one `Dealer` — zero orphans |
| 13.2 | Two seed runs of the dealer generator are byte-identical (same discipline as gate 1.6) |
| 13.3 | Zero generated dealer names match the real-dealer/brand denylist |
| 13.4 | `condition` is a working search filter: a `new`-only query returns zero `used` rows |
| 13.5 | Dealer name, city, rating and verification status render on a real `CarCard` in a browser |
| 13.6 | Every seeded seller account resolves to a dealer; every dealer to ≥1 listing |
| 13.7 | `PayeeIdentity` for an unverified dealer reports `unverified` — never blank, never defaulted to verified |
| 13.8 | Gate 1.x still green — catalogue counts, category/brand spread, and determinism unchanged |

---

## P14 — CART

**Owns:** the cart, the dedicated checkout route, and the payee disclosure that renders before any
money moves. Proposal doc #8.

### Objective

The buyer browses in chat, adds a car to a cart from a recommendation card, and completes payment on
a dedicated page — where, **before** the pay button, they are told exactly who is receiving the money
and where that business physically is.

### Scope

**In**
- `[MVP]` `src/domain/cart.py` — `Cart`, `CartItem` (`listing_id`, `source`, `source_id`,
  `offer_type`, `added_at`). Pure, no db, no clock (`now` passed in)
- `[MVP]` `src/adapters/cart_store.py` + `src/adapters/db/cart_store.py`
- `[MVP]` API: `GET /cart`, `POST /cart/items`, `DELETE /cart/items/{item_id}` — all account-scoped
  from the bearer token, never from a client-supplied account id
- `[MVP]` Cart icon with a live count in the buyer header, on every buyer route
- `[MVP]` An `add_to_cart` action on `CarCard`, dispatched through P6's **existing** action
  round-trip (`POST /sessions/{id}/actions`, the path gate 6.5 already proves), not a new channel
- `[MVP]` `/cart` route: line items, totals, the mounted checkout App, **and the live chat rail
  beside it** — same session, same SSE stream, the agent still answering while the buyer reviews
  (§0.1). This is what makes "without leaving the conversation" literally true on this route
- `[MVP]` Style the checkout App to match the site (§0.1.3) — it is plain HTML/CSS you own, and
  nothing about MCP-App compliance requires it to look like an embedded widget
- `[MVP]` **Payee disclosure panel** — legal name, full address, phone, verification status, rendered
  above the fold and above the pay control, next to the existing `MOCK — NO REAL PAYMENT` banner
- `[MVP]` An explicit, visually distinct `PAYEE IDENTITY UNVERIFIED` state — a flag, never silence
- `[MVP]` Migration `0005_cart.py`
- `[SCALE]` Multi-item checkout. **v1 is one car per checkout** — a cart may hold several, but
  checkout runs on one line item, because P8's booking lifecycle, quote path and gesture token are
  all single-listing today and widening them is a real change, not a loop
- `[SCALE]` Cart persistence across devices, abandoned-cart recovery

**Out**
- Any new payment path whatsoever (§0.1).

### The invariant this phase must not break

`confirm_booking` stays invisible to the model, still requires a gesture token minted on a trusted
click, still idempotent, still server-side priced. The cart page **must not** pre-mint a token,
must not call `submit_booking_draft` on the buyer's behalf, and must not carry a client-supplied
price into checkout. The sequence is unchanged and non-negotiable:

```
add to cart → /cart → open_checkout → [human clicks Pay] → mint_gesture_token → confirm_booking
```

### Dependencies

P7 (`McpAppHost`), P8 (checkout App, booking lifecycle, gesture tokens), P12 (account scope),
P13 (payee identity).

### Exit gate — `scripts/gate_phase14.py`

| # | Criterion |
|---|---|
| 14.1 | Add-to-cart from a real `CarCard` click reaches the cart; count badge updates without a reload |
| 14.2 | `/cart` mounts the **same** `ui://checkout/payment` resource — asserted from the browser by resource URI, not from config |
| 14.3 | The chat rail is mounted and live on `/cart`: a message sent from the cart page reaches the agent and its reply renders, without navigating away |
| 14.4 | Payee legal name, address and phone render above the fold and above the pay control |
| 14.5 | An unverified dealer renders the explicit unverified state; a verified one does not |
| 14.6 | Static scan: exactly one code path reaches `confirm_booking`, and it is the gesture-gated one |
| 14.7 | No agent-driven path adds to cart or opens checkout without a real click — zero calls, Playwright-asserted (the shape gate 8.3 uses) |
| 14.8 | Gates 8.3 / 8.6 / 8.10 / 8.11 still green — the **in-chat** checkout mount is unregressed |
| 14.9 | Double-submit from `/cart` with one idempotency key produces one booking, two identical responses |
| 14.10 | A cart item for a withdrawn or expired listing is rejected at checkout with a distinct, non-spinner UI state |
| 14.11 | Cart is account-scoped: account A's token never reads account B's cart |
| 14.12 | `DEMO_MODE=true` walks add-to-cart → `/cart` → mock pay with the environment otherwise unset |

---

## P15 — SELLER CONSOLE

**Owns:** the seller-facing half of the product. A scored, routed, notified lead — the thing a
dealership would actually pay for. Proposal doc #7.

### Objective

When a buyer engages with a listing, the seller who owns it learns: who the buyer is, what they
asked for, which car they chose, and an estimated purchase intent with the reasoning attached.

### Scope

**In**
- `[MVP]` `src/domain/lead.py` — pure:
  - `Lead`: `id`, `buyer_account_id`, `dealer_id`, `listing_id`, `requirement_summary`,
    `created_at`, `state` (`new` | `viewed` | `contacted` | `closed`)
  - `IntentTier` StrEnum: `high` | `medium` | `low`
  - `LeadSignal`: `name`, `value`, `weight`, `contribution` — the `ScoreBreakdown` shape
  - `LeadScore`: `tier`, `score`, `signals: tuple[LeadSignal, ...]`, `explanation`
- `[MVP]` `src/domain/lead_scoring.py` — deterministic, pure, stdlib+pydantic only, the same bar
  `src/domain/scoring.py` is held to (gate 5.9). Signals:

  | Signal | Source | Note |
  |---|---|---|
  | Target-date proximity | `RequirementProfile.target_date` | Primary signal, stated not inferred |
  | Budget fit vs. listing price | profile + listing | |
  | Added to cart | P14 | Strong behavioural signal |
  | Opened checkout | P14 | Strongest short of confirming |
  | Booking form submitted | P8 draft | |
  | Corporate customer | `CustomerType` | Fleet path, per proposal #6 |
  | Return sessions | P4 session store | |
  | Income band | §0.3 | **`undisclosed` is neutral, never negative** |

- `[MVP]` Tier → SLA mapping, surfaced as a countdown per lead:

  | Tier | Meaning | Dealer action |
  |---|---|---|
  | High (estimated) | Buying in ~2–3 days | Call immediately |
  | Medium (estimated) | Buying in ~1–2 weeks | Call within 1–2 days |
  | Low (estimated) | 3–6 months, gathering information | Per the dealer's own cadence |

- `[MVP]` Lead created when a buyer adds to cart, opens checkout, or submits a booking form on a
  listing owned by that dealer — **not** on a bare search impression
- `[MVP]` API: `GET /seller/leads`, `GET /seller/events` (SSE, §0.4),
  `POST /seller/leads/{id}/contacted`, all seller-token-scoped
- `[MVP]` `/seller` route: leads sorted by tier then recency; buyer name and contact; the chosen car
  with dealer attribution; an expandable **"why this tier"** showing every named signal and its
  contribution; SLA countdown; mark-contacted
- `[MVP]` Basic analytics: lead volume by tier over time
- `[MVP]` Migration `0006_leads.py`
- `[SCALE]` Email/SMS notification, conversion tracking, per-salesperson auth, lead reassignment

### Privacy rule — write this down before building the table

A buyer's phone and email are released to a seller **only after that buyer has taken an intent
action on that seller's listing** (cart-add at minimum). Browsing does not expose contact details,
and no seller ever sees a buyer who never engaged with their inventory. Income band is **never**
shown to a seller in any tier — it is an input to the score, not an output on the screen.

This is a real product rule, not a nicety: a dashboard that dumps every visitor's phone number is
the version of this feature that gets the product thrown out of a compliance review.

### Dependencies

P12 (both roles), P13 (dealer to route to), P14 (the two strongest signals), P3/P4 (profile,
sessions).

### Exit gate — `scripts/gate_phase15.py`

| # | Criterion |
|---|---|
| 15.1 | Every qualifying buyer action produces exactly one `Lead`, routed to the dealer owning that listing |
| 15.2 | Tier is deterministic: same signals, same tier and same score, twice |
| 15.3 | Every tier traces to named signals whose contributions sum to the score within 1e-9 (gate 5.2's shape) |
| 15.4 | A new lead reaches an open `/seller/events` stream within one push cycle |
| 15.5 | Seller A never sees seller B's leads — asserted per store, inside the query, not filtered afterward (CONSTITUTION IV.4) |
| 15.6 | A buyer who only browsed produces no lead and exposes no contact details |
| 15.7 | `income_band` appears nowhere in any seller-facing payload |
| 15.8 | Every tier label renders as an estimate with its reasoning, never as an assertion — asserted on rendered text |
| 15.9 | An `undisclosed` income band scores identically to a withheld one — no hidden penalty |
| 15.10 | `DEMO_MODE=true` drives a seeded buyer to produce a live lead on a seeded seller's dashboard, no keys |

---

## P16 — VOICE

**Owns:** speech in and speech out for the buyer conversation. `PLAN-01` P12, re-sequenced.

### Objective

Three independent controls: **the agent speaks its replies**, **which voice it speaks in**, and
**the buyer speaks instead of typing**. Voice is I/O only — it never touches the phase machine,
`RequirementProfile`, or slot extraction.

### Scope

**In**
- `[MVP]` Three controls in the buyer header, independently switchable, persisted per browser
  session: **agent voice on/off**, **voice picker** (which voice the agent speaks in), and
  **push-to-talk**
- `[MVP]` `POST /voice/speak` — **ElevenLabs `eleven_turbo_v2_5`, streamed mp3, as the primary
  path**, with the quota-exhaustion handling `PLAN-01` P12 documented (check the error body for
  `payment_required`/`paid_plan`, try the fallback voice id, then degrade)
- `[MVP]` `POST /voice/transcribe` — **Whisper via Groq (`whisper-large-v3-turbo`) as the primary
  path**, OpenAI Whisper as the paid fallback
- `[MVP]` The **degradation cascade** (§ below) — the mechanism that lets the good voice be the
  default without breaking a keyless machine
- `[MVP]` Browser-native Web Speech API (`SpeechRecognition` / `speechSynthesis`) as tier 2 of that
  cascade, and text as tier 3
- `[MVP]` Push-to-talk with a visible recording state and a visible transcript **before send** — the
  buyer confirms what was heard before it becomes a turn. Never auto-send a transcription
- `[MVP]` `DEMO_MODE` canned transcripts, mirroring the source project's cycling `DEMO_TRANSCRIPTS`
  array and Cardinal's own `DEMO_MODE` philosophy
- `[SCALE]` Barge-in (interrupting the agent mid-sentence), streaming TTS as the agent composes,
  per-listing audio summaries

**Out — deliberately not ported**
- The source project's multi-provider **LLM** router. Cardinal's reasoning stays on the Claude Agent
  SDK; voice is transport, it does not change who does the thinking.
- Its anxiety-detection heuristic — interview-specific, irrelevant here.

### The degradation cascade — how ElevenLabs gets to be the default

The brief says nothing about voice, so nothing here is a compliance question. The only real
constraint is **CONSTITUTION III.7**: the complete flow must run with the entire environment unset.
That does not require the *best* voice path to be keyless — only that *a* path always works.

So the good voice is the default, and the fallback is automatic and silent:

| Tier | Speech out | Speech in | Active when |
|---|---|---|---|
| **1 — primary** | ElevenLabs `eleven_turbo_v2_5` | Groq Whisper `large-v3-turbo` | Keys present |
| **2 — fallback** | `speechSynthesis` | `SpeechRecognition` | No keys, quota exhausted, or provider error |
| **3 — floor** | Text only | Typed input | No mic permission, unsupported browser |

Each tier is chosen per call, not per session, so a mid-demo quota exhaustion drops to tier 2 without
a reload and without a dead button. Selection is logged as a span attribute so a trace says which
tier actually served each turn — otherwise "the voice sounded worse today" is unfalsifiable.

`DEMO_MODE` runs tier 2 with canned transcripts, which is what keeps gate 16.2 and III.7 true. **Set
the keys for the recorded demo video** — that is the version worth showing judges, and the cascade
means the repo still passes on a machine that has never seen a key.

### Credentials

Env-var names only — **no key values from any other project.** Every one of these must be added to
`.env.example` or gate 11.7 fails.

| Variable | Purpose |
|---|---|
| `ELEVENLABS_API_KEY` | TTS, tier 1 |
| `ELEVENLABS_VOICE_ID` | Default voice for the picker |
| `GROQ_API_KEY` | Whisper STT, tier 1 — free tier, fast |
| `OPENAI_API_KEY` | Whisper STT, paid fallback within tier 1 |

Pull fresh keys from each provider's own dashboard into Cardinal's own gitignored `.env`. **Do not
reuse another project's key values** — secrets stay scoped per repo, and a key pasted from the
interview-agent repo is a key that leaks two projects at once.

### Dependencies

P3 (the turn loop it attaches to), P12 (header it lives in).

### Exit gate — `scripts/gate_phase16.py`

| # | Criterion |
|---|---|
| 16.1 | All three controls work independently; state survives a reload |
| 16.2 | `DEMO_MODE=true` completes a voice turn with every voice env var unset — tier 2 serves it (gate 3.3's discipline, CONSTITUTION III.7) |
| 16.3 | With keys present, a voice turn is served by tier 1 — asserted from the span attribute, not from config |
| 16.4 | A simulated ElevenLabs quota error mid-session drops to tier 2 **without a reload** and without a dead control |
| 16.5 | A denied mic permission falls back to tier 3 with no turn or phase state lost |
| 16.6 | A TTS failure never blocks or delays the text reply |
| 16.7 | Transcript is shown and confirmable before it becomes a turn — no auto-send |
| 16.8 | Changing the voice in the picker changes the voice of the next utterance |
| 16.9 | Every turn records which tier served it as a span attribute |
| 16.10 | `.env.example` covers every new variable (gate 11.7 re-run, not re-read) |
| 16.11 | No key value from any provider appears in source, deps, or either lockfile (extends `gate_common.py`'s scan) |

---

## 2. Cross-cutting work

None of this belongs to one phase; all of it breaks the build if missed.

### 2.1 Frontend routing

`react-router-dom` added; four routes: `/login`, `/` (buyer chat — today's app, moved unchanged),
`/cart`, `/seller`. A route guard redirects unauthenticated users to `/login` and sends a seller
landing on `/` to `/seller`. Do the router migration as its own commit with the buyer experience
provably unchanged before adding a single new route.

### 2.2 nginx and Vite proxy — the one that will bite

`web/nginx.conf` proxies backend prefixes **explicitly**; anything unlisted silently falls through to
the SPA fallback and returns `index.html` with a `200`, which parses as empty and fails with no error
anywhere. `DECISIONS.md` D-057 is exactly this bug, already paid for once.

Each new prefix — `/auth/`, `/cart`, `/seller/` — needs a block in **both** `web/nginx.conf` and
`web/vite.config.ts`, and `/seller/events` needs its own **unbuffered** block mirroring the existing
`^/sessions/[^/]+/events$` one, or the seller dashboard's SSE stream will buffer and appear dead.

Watch the same exact-match trap D-057 records: `location /cart` as a prefix would also capture any
future `/cart-*` static path. Use `location = /cart` or a trailing slash deliberately, not by habit.

### 2.3 Migrations

`0003_identity` → `0004_dealers` → `0005_cart` → `0006_leads`, in build order. `0004` backfills
`dealer_id` on existing listings — write the backfill, do not require a reseed, and keep the column
nullable until the backfill is proven before making it `NOT NULL`.

### 2.4 Layer boundary

`src/domain/{identity,dealer,cart,lead,lead_scoring}.py` import nothing but stdlib and pydantic.
Auth routes live in `src/api`, stores in `src/adapters`. `tests/test_layer_boundary.py` and the ruff
ban both already enforce this (gate 0.3) — they will catch a `fastapi` import in the domain, which is
the easiest mistake to make when writing an auth model.

### 2.5 `DEMO_MODE` survives all of it

CONSTITUTION III.7. Seed one buyer and one seller account, one dealer, one cart, one lead. The
seven-beat e2e (`web/tests/demo-e2e.spec.ts`) grows to cover login → chat → add to cart → `/cart` →
mock pay → seller sees the lead. Gates 3.3, 11.4 and 12.9/14.12/15.10/16.2 all assert the same
property from different angles, on purpose.

### 2.6 Bookkeeping

- `Makefile`: `PHASES := 0 1 2 ... 16`
- `PROGRESS.md`: real gate output pasted per phase (III.1). Nothing is "done" because it looks right
- `DECISIONS.md`: §0.1–§0.5 become real `D-0NN` entries when their code lands (III.5)
- `specs/{spec,plan,tasks}.md`: kept current as phases land (CONSTITUTION V)
- `README.md`: the two-sided flow, the demo accounts, and the dummy OTP codes documented explicitly

---

## 3. Risks

| Risk | Mitigation |
|---|---|
| `/cart` quietly becomes a second payment path and deletes CONSTITUTION I.2 | §0.1; gate 14.6 statically asserts exactly one path to `confirm_booking`; gate 14.8 keeps the in-chat mount green |
| The router migration breaks the working buyer app days before submission | Its own commit, buyer experience unchanged, gate 11.3's seven-beat e2e re-run before anything new is added |
| A new API prefix falls through to the SPA fallback and fails silently | §2.2, precedent D-057; every new prefix added to nginx **and** vite in the same commit |
| Income data turns into a privacy incident | §0.3 — exact figure captured but contained: never leaves the buyer's account, only the derived band travels, redacted in traces, never modelled, never shown to sellers (gates 12.6, 12.7, 12.8, 15.7) |
| Dummy auth gets mistaken for real auth by a judge or a future contributor | §0.2 — unconditional banner, no JWT, no secret, denylist scan (gates 12.2, 12.3) |
| Lead tiering reads as an absolute judgement about a person | §0.5 — estimate phrasing with reasoning attached, gate 15.8 asserts it on rendered text |
| Sellers see buyers who never engaged with them | §P15 privacy rule, gates 15.5 / 15.6 |
| Voice becomes a hard dependency on a keyed service | §P16's three-tier cascade — ElevenLabs/Groq is the default, browser-native catches a missing key or an exhausted quota per call; gates 16.2 / 16.4 assert both directions |
| Five phases don't fit the remaining time | Sequencing §1 is also the cut order: drop P16, then P15's analytics, then P14's `[SCALE]` lines. **Never** cut an `[MVP]` line from an earlier phase to reach a later one (III.3) |
| `condition` silently invalidates D-003's depreciation assumption | Called out in P13; either the curve becomes condition-aware or the approximation is written down |

---

## 4. What this document does not cover

Still roadmap, still unbuilt, deliberately out of scope here: **P17 trade-in** (its own flow and its
own `VehicleAppraisalProfile`, not fields bolted onto the buyer interview), **P18 buyer decision
tools** (financing comparison, insurance quotes, test-drive scheduling, warranty comparison, side-by-
side vehicle comparison), **P19 saved searches and price alerts** (needs an outbound notification
channel nothing here has), a **real dealer-directory scraper** (legal check first), **service-history
verification** (a data-sourcing decision, not an engineering one), and **multi-tenancy**.

Two hackathon-submission items also remain outside every phase here and are not made easier by any of
it: **recording the demo video**, and **running gate 11.8 for real** — a person who did not write this
repo, on a machine that has never seen it, following `README.md` verbatim. Both are still blocking
submission, and both are still worth doing before a single line of P12 gets written.
