# Progress

The only source of truth for what exists (CONSTITUTION III.4). The plan docs describe *intent* and
are deliberately not kept in sync with this file. If it isn't here, it isn't built.

A phase is done when `make gate PHASE=N` prints green and its **real output** is pasted below —
never "the code looks right" (CONSTITUTION III.1).

| Phase | State | Gate |
|---|---|---|
| **0 — FOUNDATION** | ✅ **Done** | **7/7 PASS** |
| **1 — INVENTORY** | ✅ **Done** | **10/10 PASS** |
| **2 — MCP** | ✅ **Done** — registry manifest deferred, `[SCALE]` | **7 PASS, 1 PENDING** |
| **3 — AGENT** | ✅ **Done** | **8/8 PASS** |
| **4 — MEMORY** | Partial — `[MVP]` done, `[SCALE]` deferred | **3 PASS, 5 PENDING** |
| **5 — REASONING** | `[MVP]` done, `[SCALE]` deferred | **9 PASS, 1 PENDING** |
| **6 — GENERATIVE-UI** | `[MVP]` done, `[SCALE]` deferred | **9 PASS, 1 PENDING** |
| **7 — MCP-APPS** | ✅ **Done** | **10/10 PASS** |
| **8 — COMMERCE** | ✅ **Done** | **12/12 PASS** |
| **9 — OBSERVABILITY** | `[MVP-bonus]` done, `[SCALE]` deferred | **7 PASS, 2 PENDING** |
| **10 — TRUST** | `[MVP]` done, `[SCALE]` deferred | **4 PASS, 5 PENDING** |
| **11 — DELIVERY** | `[MVP]` done, `[SCALE]` deferred | **8 PASS, 3 PENDING** |
| **12 — IDENTITY** | ✅ **Done** — `[MVP]` complete, `[SCALE]` deferred | **10 PASS, 1 PENDING** |
| **13 — DEALER** | ✅ **Done** | **8/8 PASS** |
| **14 — CART** | ✅ **Done** | **12/12 PASS** |
| **15 — SELLER CONSOLE** | ✅ **Done** | **10/10 PASS** |
| **16 — VOICE** | ✅ **Done** — `[MVP]` complete, `[SCALE]` deferred | **11 PASS, 1 PENDING** |
| **Design system + front page** | ✅ **Done** — Paddock Green; not a phase, no gate of its own | **every existing gate re-run green** |
| **Demo-banner removal** | ✅ **Done** — D-091; CONSTITUTION I.5 revised | **17/17 gates re-run green** |

---

## Demo-banner removal ✅ — D-091

Removed the four on-screen mock/demo disclosure banners at the product owner's request: the
`DEMO AUTH` strip and visible OTP codes on `/login`, the front-page announcement bar, and
`MOCK — NO REAL PAYMENT` on checkout. The fourth is the one CONSTITUTION I.5 named explicitly;
confirmed as a deliberate choice after being told it would override the constitution and turn
gate 8.10 red. Full reasoning, and what stayed honest underneath (the API still discloses the
banner text and demo codes in JSON; the MCP resource description still says "MOCK"; README and
DECISIONS.md still state it in prose), is in D-091.

Found and fixed in the same pass, reported by the product owner from a live screenshot: three
`<select>` elements (`login-form select`, the shared `.ui-select`, `.voice-picker`) rendered
their open option list as white text on the browser's own unstyled white popup — invisible,
not merely low-contrast, because `color` set on a closed `<select>` does not reach the popup
surface the browser paints for `<option>`. Fixed by styling `option` directly at all three call
sites.

```
GATE 0  GREEN            GATE 6  GREEN (1 pending)     GATE 12 GREEN (2 pending)
GATE 1  GREEN            GATE 7  GREEN                 GATE 13 GREEN
GATE 2  GREEN (1 pend)   GATE 8  GREEN                 GATE 14 GREEN  12/12
GATE 3  GREEN (1 pend)   GATE 9  GREEN (2 pending)     GATE 15 GREEN  10/10
GATE 4  GREEN (6 pend)   GATE 10 GREEN (5 pending)     GATE 16 GREEN (1 pending)
GATE 5  GREEN (1 pend)   GATE 11 GREEN (6 pending)
```

Plus ruff, `ruff format --check` (201 files), `mypy --strict src/domain`, `mypy` over
agent/adapters/api/mcp, and 880 tests passing / 64 skipped — all clean.

### What shipped

| Area | Files |
|---|---|
| Banner removal | `web/src/auth/LoginPage.tsx`, `web/src/routes.tsx`, `web/src/showroom/ShowroomPage.tsx`, `src/mcp/booking/static/checkout.html` |
| CSS cleanup | `web/src/styles.css`, `web/src/showroom/showroom.css` — `.demo-banner`, `.demo-codes`, `#mock-banner`, `.showroom-announce*` rules removed |
| The `<select>` fix | `web/src/styles.css` (`.login-form select option`, `.voice-picker option`), `web/src/ui/ui.css` (`.ui-select option`) |
| Constitution | `CONSTITUTION.md` I.5 revised in place with the override recorded, not deleted |
| Gates re-scoped | `scripts/gate_phase8.py` (8.10), `scripts/gate_phase12.py` (12.2) — criteria renamed to what they now check |
| Specs | `tests/auth.spec.ts`, `tests/commerce.spec.ts`, `tests/cart.spec.ts`, `tests/demo-e2e.spec.ts`, `tests/open-app.spec.ts` |
| README | Accounts-and-login row reworded: dummy, disclosed in the API rather than on screen |

### Worth knowing

- **Gate 8.10 and 12.2 now assert absence, not presence.** Each spec confirms the removal was
  deliberate and complete — no banner text anywhere in the rendered page — rather than simply
  deleting the assertion and leaving the criterion number pointing at nothing.
- **The apparent gate 14 failure on the first re-run was resource contention, not a
  regression.** A dozen leftover Vite/Playwright/uvicorn processes had accumulated across the
  session on ports 5199–5201 and 8000/8200; killing them and re-running gates 8 and 14 alone
  produced clean green. Worth remembering: a cascading "everything failed" result across
  unrelated browser criteria is a environment-contention smell before it's a code smell.

---

## Design system + front page ✅ — Paddock Green

Not a phase and it has no gate of its own, so the only honest evidence is that **every gate that
already existed was re-run and is still green**. Two passes landed here, in order: a white
Cohere canvas (D-089) and then the dark, photographic **Paddock Green** re-theme the product
owner handed off (D-090). What is described below is what is in the tree now. Re-run on
2026-08-09, after the re-theme.

```
GATE 0  GREEN            GATE 6  GREEN (1 pending)     GATE 12 GREEN (2 pending)
GATE 1  GREEN            GATE 7  GREEN                 GATE 13 GREEN
GATE 2  GREEN (1 pend)   GATE 8  GREEN                 GATE 14 GREEN  12/12
GATE 3  GREEN (1 pend)   GATE 9  GREEN (2 pending)     GATE 15 GREEN  10/10
GATE 4  GREEN (6 pend)   GATE 10 GREEN (5 pending)     GATE 16 GREEN (1 pending)
GATE 5  GREEN (1 pend)   GATE 11 GREEN (6 pending)
```

Plus `ruff check`, `ruff format --check` (201 files), `mypy --strict src/domain` and `mypy` over
`agent/adapters/api/mcp` — all clean — and 880 tests passing, 64 skipped.

**The re-theme required no spec changes at all.** Every gate that had to be repaired belonged to
the earlier route move (D-088), not to the colour: gate 12 needed two real code fixes and gate
14.1 asserted the chat's URL. That the paddock pass touched no test is the strongest available
evidence that it really was a token edit rather than a rewrite.

### What shipped

| Area | Files |
|---|---|
| Token layer | `web/src/ui/tokens.css` — Paddock Green palette (`--pg-*`) published under shadcn's semantic token names, over Cohere's radius/spacing/type ladders, plus the legacy `--bg`/`--text`/`--line`/`--accent` aliases `styles.css` reads |
| Component kit | `web/src/ui/` — `Button`, `Card` (7 parts), `Badge`, `Input`/`Textarea`/`Select`/`Label`/`Field`, `Separator`, `Tabs` (full WAI-ARIA tabs: roving tabindex, orientation-aware arrows, Home/End), `cn`, `Slot`, `ui.css`. No new npm dependency |
| Front page | `web/src/showroom/{ShowroomPage.tsx,showroom-data.ts,showroom.css}` — full-bleed photographic stage with a left-to-right scrim, eyebrow → two-line display headline → blurb → price pair → two CTAs, an overlaid spec rail with a verified-seller chip, capability row, trust band, footer |
| Photography | `web/public/showroom/hero-paddock-{1280,1920,3840}.{jpg,webp}` (2.4:1 band cropped from a 5756×4000 source) and `login-m5-{620,1240}.{jpg,webp}`; `<picture>` with WebP first, `fetchPriority="high"` on the LCP image |
| Routes | `web/src/routes.tsx` (`/` showroom, `/chat` agent), `web/src/SiteHeader.tsx`, `web/src/auth/destination.ts` |
| Two-column sign-in | `web/src/auth/LoginPage.tsx` — existing JSX wrapped in `.login-col`, plus a decorative `aria-hidden` photo column. No field, validation or handler changed |
| Empty canvas | `web/src/App.tsx` — `PhaseBars` / `PhaseLabels`, derived from the `phase` the SSE stream already reports; replaced three shimmering placeholder bars |
| Restyle | `web/src/styles.css` — ambient mesh re-tuned, header/rail/composer/cart/seller surfaces, flat coral demo banner, mint/coral tier and signal treatment |
| Seller detail | `web/src/seller/SellerConsole.tsx` — contribution sign derived rather than hardcoded, `data-sign` on each signal row |

Design sources: the **Paddock Green handoff** (`design_handoff_paddock_green_theme/`) for the
colour, layout and photography; `shadcn-ui/ui` (`registry/new-york-v4`) for the component anatomy
and token vocabulary; Cohere (`VoltAgent/awesome-design-md`) for the radius, spacing and type
ladders, which the re-theme left untouched.

### Worth knowing

- **The token layer is the whole trick, and it has now been tested twice.** White → paddock green
  was one file plus four things that encoded an assumption about the *ground* rather than a
  colour: the ambient mesh, the shadow scale, `--danger` reaching `.tier-high`, and the
  demo-auth banner's translucency. See D-090.
- **CSS import order in `main.tsx` is load-bearing.** The three stylesheets sit *above* the
  `routes` import. Vite emits CSS in module-graph order, so importing `routes` first pulled
  `showroom.css` in ahead of the kit and let `ui.css` override the page composing it.
- **`live-chat.spec.ts` and `model-picker.spec.ts` were already broken by D-085** and nobody had
  noticed: both opened `/` anonymously and waited for the chat input. They are not in any gate
  (`playwright.live.config.ts` is run by hand against a keyed stack). Fixed rather than left.

### Deferred, deliberately

- **The showroom is a showcase, not a listing.** Its performance figures are BMW's published
  numbers; the asking price, monthly, mileage and seller are illustrative, and the ⓘ control
  says so. Wiring the hero to a real `Listing` — so the CTA opens the agent already holding that
  car — is the obvious next step and is not built.
- **No cart-line photo thumbnail.** Listed as optional in the handoff. Cart lines carry no
  photograph in the data model, and putting a picture of a car that is not the car beside a
  payee disclosure would undercut the most carefully honest surface in the product (D-090).
- **Light theme removed.** The design commits to one visual world; `color-scheme: dark`.
- **The `[SCALE]` lines in every phase above are untouched.** Both design passes were
  presentation only: no domain, agent, MCP or adapter code changed.

---

## Phase 16 — Voice ✅

`plans/PLAN-02-MARKETPLACE.md`'s last phase, and the only one whose whole design is a failure
mode. Run on 2026-08-09 with the voice environment **scrubbed** — every criterion proves the
*cascade*, not that ElevenLabs is reachable. That is deliberate: a criterion needing a funded
account could only ever run on one machine, which is the opposite of what a gate is for.

```
==============================================================================
GATE 16 -- VOICE -- three-tier cascade, picker, push-to-talk
==============================================================================
  16.1   PASS     all three controls work independently; state survives a reload
           web/tests/voice.spec.ts passed in a real Chromium -- stats={'expected': 4,
           'unexpected': 0, 'flaky': 0, 'skipped': 0}
  16.2   PASS     DEMO_MODE completes a voice turn with every voice env var unset (tier 2)
           transcribe -> 200 tier='browser' text="I'm looking for a family SUV, budget
           a"...; speak -> 204 (browser speaks); ELEVENLABS/GROQ/OPENAI keys all unset
  16.3   PASS     with a provider wired, a voice turn is served by tier 1
           speak -> 200 X-Voice-Tier='provider'; transcribe -> 200 tier='provider' (stub
           provider: this asserts tier *selection*, not ElevenLabs reachability)
  16.4   PASS     a mid-session quota error drops to tier 2 without a reload or a dead control
           three consecutive utterances served ['provider', 'browser', 'provider'] -- the
           quota failure degraded the second only; no reload, and tier 1 resumed on the third
  16.5   PASS     a denied mic falls to tier 3 with no turn or phase state lost
           select_tier(provider=False, browser=False) -> 'text';
           /voice/capabilities?browser=false reports text for both directions
  16.6   PASS     a TTS failure never blocks or delays the text reply
           a raising synthesiser produced 204 X-Voice-Tier='browser', never a 5xx
  16.7   PASS     the transcript is shown for confirmation, never auto-sent
           transcribe created 0 turns; web/src/voice/api.ts contains no reference to
           postMessage, so no code path runs mic -> turn
  16.8   PASS     the picker offers provider voices only when a provider exists
           no key -> 1 voice ('System voice'); provider wired -> 4 voices, 3 of them tier 1
  16.9   PASS     every voice call records which tier served it, as a span attribute
           voice.speak tier='provider', voice.transcribe tier='provider' -- 'the voice
           sounded worse today' is falsifiable
  16.10  PASS     .env.example documents every voice variable the code reads
           4 voice variables, all present in .env.example
  16.11  PASS     no provider key value appears in source, deps or either lockfile
           206 files scanned for 4 live-credential prefixes, 0 hits -- every key is read
           from the environment at call time
  16.12  PENDING  [SCALE] barge-in and streaming TTS as the agent composes
           barge-in (interrupting the agent mid-sentence) and streaming synthesis are
           PLAN-02 P16's own [SCALE] lines -- deferred per CONSTITUTION III.3
------------------------------------------------------------------------------
  11 passed, 0 failed, 1 pending
  GATE 16 GREEN (with 1 pending)
==============================================================================
```

### What shipped

| Area | Files |
|---|---|
| Tier vocabulary + pure selection | `src/domain/voice.py` — `VoiceTier`, `TIER_ORDER`, `select_tier` (total), `next_tier`, `VoiceOption`, `VoiceCapabilities`, `Utterance` |
| Provider seams | `src/adapters/voice/protocol.py` — `SpeechSynthesizer`/`SpeechTranscriber`, `VoiceError`/`QuotaExhausted`, `env_key` (empty string counts as unset) |
| Tier-1 providers | `src/adapters/voice/providers.py` — `ElevenLabsSynthesizer` (`eleven_turbo_v2_5`, voice-id fallback chain, quota detection by body marker), `WhisperTranscriber` (Groq first, OpenAI as the paid fallback *within* tier 1) |
| The cascade | `src/adapters/voice/cascade.py` — per-call tier selection, `DEMO_TRANSCRIPTS` cycling **per session**, `MIN_AUDIO_BYTES` guard |
| Transport | `src/api/voice.py` — `GET /voice/capabilities`, `POST /voice/speak`, `POST /voice/transcribe`; `X-Voice-Tier` on every response, `voice.tier` on every span |
| Frontend | `web/src/voice/{recorder.ts,api.ts,VoiceControls.tsx}`, wired into `web/src/App.tsx`; `web/src/styles.css` (+P16 block) |
| Config | `.env.example` — the four voice variables, documented with the cascade table |
| Gate | `scripts/gate_phase16.py`, `web/tests/voice.spec.ts`, `web/playwright.voice.config.ts` |
| Tests | `tests/unit/test_voice_cascade.py` (22), `tests/integration/test_api_voice.py` (9) |

**Four implementation details came from studying a prior voice project** (`D:\Interview Agent`)
rather than from the plan, and each one is a bug that would otherwise have been found late:

- **The recording MIME type must be probed, not assumed.** Safari supports neither
  `audio/webm` nor Opus; hardcoding either yields a `MediaRecorder` that constructs and then
  produces nothing. `web/src/voice/recorder.ts` walks `isTypeSupported` in preference order.
- **`MediaRecorder.start(250)`.** With no timeslice a short press can emit a single empty
  `dataavailable` at stop, producing a 0-byte blob and a baffling "too short" error.
- **A minimum-bytes guard before spending a provider call.** Under 500 bytes there is no
  speech; asking anyway costs a call and returns an empty transcript that reads to the user as
  "it ignored me".
- **The upload's filename extension is load-bearing.** Whisper's multipart endpoints key off
  it rather than the part's content-type, so `speech.bin` is rejected as an unsupported format
  even with a correct MIME type. Mirrored on both sides (`_extension` / `api.ts`).

Two things that project does were **deliberately not ported**: its multi-provider *LLM* router
(Cardinal's reasoning stays on the Claude Agent SDK — voice is transport, it does not change
who does the thinking) and its anxiety-detection heuristic (interview-specific, and the kind of
inference about a person this product has no basis to make).

One improvement on the source: its demo transcripts advance from a single module-level counter,
so two browsers open at once interleave and each sees half a script. Cardinal's cursor is keyed
per session (asserted by
`test_demo_transcripts_advance_per_session_not_globally`).

### Deferred, deliberately

- **`[SCALE]` Barge-in and streaming TTS** — gate 16.12. Interrupting the agent mid-sentence
  needs an audio pipeline that can be cancelled cleanly; PLAN-02 P16's own `[SCALE]` line.
- **`[SCALE]` Per-listing audio summaries.**
- **A live rehearsal with real ElevenLabs/Groq keys.** Every mechanism here is proven against
  stub providers and the scrubbed-environment path — which is the honest, portable thing to
  gate — but nobody has yet heard tier 1 actually speak. **Set the keys before recording the
  demo video**: tier 1 is the version worth showing, and the cascade means the repo still
  passes on a machine that has never seen a key.

---

---

## Phase 15 — Seller console ✅

`plans/PLAN-02-MARKETPLACE.md`'s fourth phase, and the seller-facing half of the product. Run
on 2026-08-09. 15.1/15.2/15.3/15.5/15.7/15.9 are pure Python (the scorer is a pure function;
the routes run through the real FastAPI app via `TestClient`). 15.4/15.6/15.8/15.10 drive a
real Chromium with **two browser contexts** — a buyer and a seller signed in simultaneously,
which is the only way to assert that an action in one reaches the other — against a backend
`scripts/gate_phase15.py` starts itself on :8125 with the environment scrubbed to
`DEMO_MODE=true`.

```
==============================================================================
GATE 15 -- SELLER CONSOLE -- lead routing, intent tiers, privacy
==============================================================================
  15.1   PASS     every qualifying action produces exactly one Lead, routed to the car's dealer
           3 actions on one car -> 1 lead carrying ['cart_add', 'checkout_opened']; a second
           car -> a second lead; both routed to the dealer that owns them (['AB-1001',
           'AB-1011'])
  15.2   PASS     the tier is deterministic: same signals, same tier and score, twice
           score=0.817345 tier=high byte-identical across two runs; event order irrelevant;
           imports ['__future__', 'datetime', 'decimal', 'src'] all stdlib/pydantic/domain
  15.3   PASS     every tier traces to named signals whose contributions sum to the score (1e-9)
           36 lead shapes checked across 3 event sets x 4 target dates x 3 budget cases; worst
           |score - sum(contributions)| = 0.00e+00; every signal named, weighted and explained
  15.4   PASS     a new lead reaches an open /seller/events stream, no reload
           15.4 a new lead reaches an open /seller/events stream without a reload
  15.5   PASS     seller A never sees seller B's leads -- scoped inside the query, not after it
           A=1 lead, B reads 0; B's POST on A's lead id -> 404 and changed nothing; anonymous
           -> 401; no seller route takes a dealer id (['/seller/dealers', '/seller/events',
           '/seller/leads', '/seller/leads/{lead_id}/contacted']); every LeadStore read
           requires one
  15.6   PASS     a browsing buyer produces no lead and exposes no contact details
           15.6 a buyer who only browsed produces no lead and exposes no contact details
  15.7   PASS     income_band appears nowhere in any seller-facing payload
           buyer holds EUR 88,000 / band '50k_100k' / employer on file; 7 terms scanned across
           4 seller-facing payloads (['/seller/dealers', '/seller/leads', '/seller/profile',
           'contacted']), 0 hits
  15.8   PASS     every tier renders as an estimate with its reasoning attached
           15.8 every tier renders as an estimate with its reasoning, never as an assertion
  15.9   PASS     no income band can change a lead's score -- undisclosed, disclosed or absent
           the scorer has no income parameter and rejects one for all 5 bands + None; three
           buyers differing only in income (none / EUR 250k / EUR 18k) all scored 0.294000
  15.10  PASS     DEMO_MODE drives a buyer action to a live seller dashboard, no keys
           15.10 DEMO_MODE drives a buyer action to a live seller dashboard with no keys
------------------------------------------------------------------------------
  10 passed, 0 failed, 0 pending
  GATE 15 GREEN
==============================================================================
```

Without `web/node_modules` + Chromium the four browser criteria report `PENDING` (gate 6.2's
convention) and the other six still run.

### What shipped

| Area | Files |
|---|---|
| Lead domain | `src/domain/lead.py` — `Lead` (id derived by `lead_uuid`, events a set, `min_length=1`), `LeadEvent`, `LeadState`, `IntentTier` (+`label`/`guidance`), `LeadSignal`, `LeadScore` (sum-check), `SLA_WINDOWS`/`sla_deadline`/`is_overdue` |
| Lead scoring | `src/domain/lead_scoring.py` — seven weighted signals summing to 1.0, three normalisers, `tier_for`, `explain`. Pure: stdlib + pydantic only, asserted by gate 15.2 |
| Stores | `src/adapters/lead_store.py` (`LeadStore` protocol — **every read takes a `dealer_id`, there is no "all"** — `InMemoryLeadStore`, `ScoreFn`), `src/adapters/db/lead_store.py` (`PostgresLeadStore`, dual-storage, `ON CONFLICT` upsert) |
| Schema | `migrations/versions/0006_leads.py` — `leads` keyed on `lead_uuid`, indexed on `dealer_id` and `(dealer_id, state)`; `LeadRow` in `src/adapters/db/models.py` |
| The lead seam | `src/api/leads.py` — `record_lead` (the one place a buyer action becomes a lead; never raises), `requirement_summary`, `lead_payload` (the seller-facing projection, built field by field), `_listing_payload` (headline + current price, resolved on read) |
| Seller transport | `src/api/seller.py` — `GET /seller/leads`, `GET /seller/events` (SSE), `POST /seller/leads/{id}/contacted`, `GET /seller/dealers`, `SellerEventHub` (one `QueueUISink` per *dealer*), `_analytics` |
| Hooks | `src/api/cart.py` (cart-add, checkout-opened), `src/api/main.py` (`_record_draft_lead` on `submit_booking_draft`) |
| Seller↔dealer link | `src/api/auth.py` — `_validate_dealer_claim`; `web/src/auth/LoginPage.tsx` — the dealership picker |
| Console | `web/src/seller/{api.ts,SellerConsole.tsx}`, `web/src/routes.tsx` (the P12 placeholder replaced), `web/src/styles.css` (+P15 block) |
| Proxy config | `web/nginx.conf` (`location = /seller/events` **unbuffered**, before `location /seller/`) and `web/vite.config.ts` (`"/seller/"`) — D-076's collision again |
| Gate | `scripts/gate_phase15.py`, `web/tests/seller.spec.ts`, `web/playwright.seller.config.ts` |
| Tests | `tests/unit/test_domain_lead.py` (20), `tests/unit/test_domain_lead_scoring.py` (32), `tests/unit/test_adapters_lead_store.py` (12), `tests/integration/test_api_seller.py` (19), `tests/integration/test_adapters_lead_store_postgres.py` (7, live Postgres) |

Four things surfaced while building this that were not in the plan:

- **Income cannot be a scoring signal and stay off the seller's screen.** The plan asks for
  both: every contributing signal visible and summing to the score (§0.5, gate 15.3), and the
  income band never shown (§P15, gate 15.7). Showing it leaks; hiding one row lets the seller
  subtract; blending it into "affordability" is invertible by a dealer who reads the
  open-source scorer next to the budget the console already shows them. **Income left the
  score** — the tier answers *how soon*, not *how much* — and gate 15.9 now asserts the
  stronger property: no band, disclosed or otherwise, can reach or move a lead score
  (DECISIONS.md D-079). This is a deliberate departure from the plan's signal table.
- **`SellerProfile.dealer_id` was never populated.** P13's scope listed it; P13's gate 13.6
  became a different criterion and nothing ever set the field, so every seller account had
  `dealer_id=None` and there was nothing to route a lead to. P15 adds the dealership picker
  at signup, validated against the directory but deliberately not *authorised* — with demo
  auth a check that enforces nothing is theatre (D-080).
- **Opening a `TestClient(app)` re-runs the app's lifespan and rebuilds `app.state`.** Gate
  15.9's first run reported "expected 3 leads, got 1" because each buyer client was opened
  inside the loop, wiping the lead store between writes. Every client is now opened before any
  of them writes. Worth remembering for any future gate that needs more than two simultaneous
  clients.
- **`/seller/events` needs its nginx block *before* `location /seller/`.** nginx's
  longest-prefix rule would otherwise hand the SSE path to the buffered block and the console's
  live feed would appear dead with nothing in any log. Same family as D-057 and D-076.
- **Replacing P12's `/seller` placeholder turned gate 12.2 red.** `auth.spec.ts` asserts a
  heading reading "Seller console" after a seller signs in — and that spec's seller picks no
  dealership, so the real console's first draft showed the *person's* name instead. Fixed in
  the console rather than in the spec: the heading is the dealership when one resolves and
  "Seller console" otherwise, because a page title should say what the page is, and a seller
  whose account was never linked (D-080) is precisely who needs to be told that. Gate 12 is
  green again.
- **A lead first showed its car as `mock_autobazaar:AB-1001`.** Nobody can phone a buyer about
  that. The payload now carries the listing headline, the *current* price (resolved on read,
  never frozen onto the lead) and whether it is still available — with the raw reference kept
  alongside, because it is what a dealer searches on.

### Deferred, deliberately

- **`[SCALE]` Email/SMS notification, conversion tracking, per-salesperson auth, lead
  reassignment.** The live dashboard answers "the seller should know"; outbound delivery is
  still the open question PLAN-01 §P17 flagged.
- **`[SCALE]` Real dealer-staff provisioning.** The picker is the seam (D-080).
- **`return_sessions` is always 1.** The signal, its weight and its normaliser are real and
  tested, but nothing counts a buyer's prior sessions yet — that needs P4's `[SCALE]` episodic
  memory to know one account's sessions are the same person across time. Written down rather
  than silently scoring everyone as a first-timer without saying so.
- **Lead state has four values; the console drives two.** `viewed` and `closed` exist on
  `LeadState` and nothing sets them. `new → contacted` is the transition a dealer actually
  makes in a demo; the other two need a CRM's worth of workflow around them.
- **The analytics strip is seven days of counts.** PLAN-02's own cut order puts analytics
  second on the list to drop; this is the small version that answers "is this getting better
  or worse" without becoming a BI tool.

---

## Phase 14 — Cart ✅

`plans/PLAN-02-MARKETPLACE.md`'s third phase. Run on 2026-08-09. Two halves, the split D-015
established: 14.6/14.8/14.9/14.11 and the server side of 14.10 are pure Python (static scans
and the real FastAPI app through `TestClient`); the rest drive a real Chromium against a
backend `scripts/gate_phase14.py` starts itself on :8124 with the environment scrubbed to
`DEMO_MODE=true` — which is also 14.12's own evidence. 14.8 **re-runs gate 8 in full** rather
than reading it (CONSTITUTION III.1), including gate 8's own browser suite.

```
==============================================================================
GATE 14 -- CART -- add to cart, payee disclosure, checkout on /cart
==============================================================================
  14.1   PASS     add-to-cart from a real CarCard click reaches the cart; the badge updates
           14.1 add-to-cart from a real CarCard click reaches the cart and updates the badge
  14.2   PASS     /cart mounts the same ui://checkout/payment resource -- read from the DOM
           14.2 /cart mounts the same ui://checkout/payment resource
  14.3   PASS     the chat rail is mounted and live on /cart, same session
           14.3 the chat rail is mounted and live on /cart
  14.4   PASS     payee legal name, address and phone above the fold and above the pay control
           14.4 payee legal name, address and phone render above the fold and above the pay
           control
  14.5   PASS     an unverified payee is flagged explicitly; a verified one is not
           14.5 an unverified payee renders the explicit unverified state; a verified one does
           not
  14.6   PASS     exactly one code path reaches confirm_booking, and it is the gesture-gated one
           1 @tool registration (src/mcp/booking/tools.py:433); code references confined to
           ['src/mcp/booking/resources.py', 'src/mcp/booking/tools.py']; the gesture token is
           consumed at statement 2 of confirm_booking (ok, reason =
           gesture_tokens.consume(args["gesture_token"], b...); ALLOWED_VIEW_TOOLS grants it to
           ui://checkout/payment only; 0 code references across 23 files in web/src
  14.7   PASS     no agent-driven path adds to cart or opens checkout -- zero, without a click
           14.7 nothing reaches the cart or checkout without a real click
  14.8   PASS     gates 8.3 / 8.6 / 8.10 / 8.11 still green -- in-chat checkout intact
           scripts.gate_phase8 exits 0 -- 8.3 PASS, 8.6 PASS, 8.10 PASS, 8.11 PASS (re-run in
           full, not read)
  14.9   PASS     double-submit from /cart with one idempotency key: one booking, two responses
           cart -> /cart/checkout -> ui://booking/form -> one booking
           (84665efc-2337-406f-9bfb-ad448c01a096), two identical responses under key
           'gate14-same-idempotency-key'
  14.10  PASS     a withdrawn cart line reports unavailable and is refused at checkout
           available flipped true -> false on withdrawal; POST /cart/checkout -> 409 'that
           listing is no longer available'; rendering PASS
  14.11  PASS     cart is account-scoped: account A's token never reads account B's
           A=1 item, B reads 0; B's DELETE and checkout on A's item_id changed nothing;
           anonymous=401; no cart route takes an account id (['/cart/checkout', '/cart/count',
           '/cart/items', '/cart/items/{item_id}'])
  14.12  PASS     DEMO_MODE walks add-to-cart -> /cart -> mock pay with the environment unset
           14.12 DEMO_MODE walks add-to-cart -> /cart -> mock pay with the environment unset
------------------------------------------------------------------------------
  12 passed, 0 failed, 0 pending
  GATE 14 GREEN
==============================================================================
```

Without `web/node_modules` + Chromium the eight browser criteria report `PENDING` (the
convention gate 6.2 established), and 14.8 reports `PENDING` too rather than claiming gate 8's
browser criteria are green when they were never run.

### What shipped

| Area | Files |
|---|---|
| Cart domain | `src/domain/cart.py` — `CartItem` (with `natural_key`), `Cart` (immutable; `with_item` idempotent on `(source, source_id, offer_type)`) |
| Stores | `src/adapters/cart_store.py` (`CartStore` protocol, `InMemoryCartStore`, `new_cart_item`), `src/adapters/db/cart_store.py` (`PostgresCartStore`) |
| Schema | `migrations/versions/0005_cart.py` — `cart_items` with `UNIQUE (account_id, source, source_id, offer_type)`; `CartItemRow` in `src/adapters/db/models.py` |
| Cart transport | `src/api/cart.py` — `GET|POST /cart/items`, `DELETE /cart/items/{id}`, `POST /cart/checkout`, `GET /cart/count`, all account-scoped from the cookie |
| Payee disclosure | `src/mcp/booking/tools.py` (`_payee_fields`, resolved server-side from the *listing's* dealer), `src/mcp/booking/static/checkout.html` (`#payee` block above the pay control), `src/mcp/booking/server.py` (`dealers` parameter) |
| Add-to-cart on the card | `src/mcp/ui/compiler.py` (`CardVisual.offer_type` → `offerType`), `src/mcp/ui/catalog.py`, `src/mcp/ui/tools.py`, `web/src/a2ui/catalog.tsx` (the button + `stopPropagation`) |
| Cart frontend | `web/src/cart/{api.ts,CartContext.tsx,CartPanel.tsx,CartBadge.tsx}`, `web/src/App.tsx` (`mode="cart"`, the `add_to_cart` action handler, the header badge), `web/src/routes.tsx` (`/cart`, buyer-guarded), `web/src/main.tsx` (`CartProvider`), `web/src/styles.css` (+P14 block) |
| Host attribution | `web/src/mcp-host/McpAppHost.tsx` — `data-resource-uri`, so gate 14.2 can read which App is mounted from the DOM rather than from config |
| Proxy config | `web/nginx.conf` (`location /cart/`) and `web/vite.config.ts` (`"/cart/"`), added in the same change (D-057's trap, D-076's collision) |
| Wiring | `src/api/main.py` — `build_cart_store`, `app.state.cart_store`, `app.state.cart_checkout_sessions`, the post-`submit_booking_draft` hand-off outside `DEMO_MODE` |
| Gate | `scripts/gate_phase14.py`, `web/tests/cart.spec.ts`, `web/playwright.cart.config.ts` |
| Tests | `tests/unit/test_domain_cart.py` (12), `tests/unit/test_adapters_cart_store.py` (9), `tests/integration/test_api_cart.py` (17), `tests/integration/test_adapters_cart_store_postgres.py` (8, run against live Postgres) |

Three things surfaced while building this that were not in the plan:

- **`/cart` collides with itself.** PLAN-02 §2.2 flagged that every new API prefix needs a
  block in nginx *and* Vite; it did not notice that `/cart` is simultaneously the buyer's page
  route and (as specified) an API route, and a proxy cannot tell a navigation from a `fetch()`
  by path alone. Every cart route therefore lives one level down — the plan's `GET /cart`
  became `GET /cart/items` — and a test asserts the bare route can never come back
  (DECISIONS.md D-076).
- **The scripted `DEMO_MODE` run opens the booking-form App by itself.** Gate 14.7's first
  draft asserted "no MCP App mounted without a click", which is wrong: `open_booking_form` is
  model-visible by design and beat 6 of the demo opens it. The criterion that actually matters
  is narrower and now says so — the agent may never open *checkout*, and may never touch the
  cart. The spec asserts the mounted resource is `ui://booking/form` and the cart count is
  still 0. It also drove the session layout: three separate agent sessions, because a scripted
  run and a cart-initiated checkout racing to mount an App over each other would fail in a way
  that looks like a cart bug.
- **Gate 14.6's own scan was too blunt to survive this repo's comments.** Its first run went
  red on `web/src/cart/api.ts` — for a comment saying the module never goes near
  `confirm_booking`. The Python half gets comment-exclusion free from `ast`; the `web/` half
  now strips comments before scanning. A scan that cannot tell an explanation from a call
  either fails on good documentation or teaches people to stop writing it, and the second
  outcome is worse than no scan.

### Deferred, deliberately

- **`[SCALE]` Multi-item checkout.** A cart may hold several cars; checkout runs on one line,
  because P8's booking lifecycle, quote path and gesture token are all single-listing and
  widening them is a real change rather than a loop. The cart page says so on screen rather
  than leaving the buyer to discover it, and `_payload` deliberately returns **no cart-wide
  total** — a sum across a rental and a purchase is a number with no meaning.
- **`[SCALE]` Cart persistence across devices, abandoned-cart recovery.**
- **The A2UI canvas is not visible on `/cart`.** Surfaces the agent composes while the buyer
  is on the cart page are processed but not drawn — the canvas slot holds the cart. The chat
  rail still narrates them (D-078). Splitting the canvas is the `[SCALE]` fix.
- **`condition` still does not influence ranking or TCO** — inherited from P13, still P16's
  `[SCALE]` territory, and now visible on cart lines as well as result cards.
- **A confirmed purchase does not empty the cart.** Not in P14's scope list, and not a
  one-liner: the success only exists inside the sandboxed checkout iframe, so the host page
  has no signal to react to without inventing a new one — and inventing a channel out of that
  iframe is exactly the kind of thing P7's isolation was built to make hard. The buyer can
  remove the line; wiring it to `confirm_booking`'s own result belongs with P15's lead events,
  which need the same signal for the same reason.
- **Gate 14.10's rendering half runs against an intercepted response.** A listing can only be
  withdrawn *after* it was added (the API refuses to add an unavailable one) and no route
  withdraws one, so the running backend cannot produce that state on demand. The server
  behaviour — `available` flipping to `false`, checkout returning 409 — is asserted in Python
  against the real app; the browser asserts the rendering of exactly that payload. Stated here
  rather than left for someone to notice.

---

## Phase 13 — Dealer ✅

`plans/PLAN-02-MARKETPLACE.md`'s second phase. Run on 2026-08-09; every criterion is pure
Python against the generated catalogue except 13.5, which drives a real Chromium against
`harness.html` (gate 6.2's own fixture harness, so the assertion is against real compiler
output through the real `carCatalog`, not hand-written JSON).

```
==============================================================================
GATE 13 -- DEALER -- directory, attribution, condition, payee identity
==============================================================================
  13.1   PASS     every listing resolves to exactly one Dealer -- zero orphans
           240/240 listings resolve to 1 dealer each across 95 distinct dealers; 0 orphans,
           0 dangling, 0 city/source mismatches
  13.2   PASS     two seed runs of the dealer generator are byte-identical
           sha256 0a35d1c62db1a967b90103959f865097... identical across two runs of 108
           dealers; seed=7 differs (f8149ae27772531c...)
  13.3   PASS     no generated dealer name matches the real-brand/dealer denylist
           108 dealer names scanned against 34 real-world terms (every brand in the live
           taxonomy + 10 known dealer groups), 0 hits; planted 'Toyota Motors Berlin'
           correctly rejected
  13.4   PASS     condition is a working filter: a new-only query returns zero used
           spread {'certified_pre_owned': 33, 'new': 10, 'used': 197}; new-only returned 10
           rows, all new; cpo-only returned 33, all certified_pre_owned
  13.5   PASS     dealer name, city, rating and verification render on a real CarCard
           web/tests/dealer-card.spec.ts rendered real compiler output through the real
           carCatalog in Chromium -- stats={'expected': 3, 'unexpected': 0, 'flaky': 0,
           'skipped': 0}
  13.6   PASS     the directory covers every city on every marketplace
           108 dealers = 2 sources x 18 cities x 3; verification spread {'pending': 23,
           'unverified': 13, 'verified': 72}; 95 hold stock
  13.7   PASS     PayeeIdentity for an unverified dealer reports it, never blank
           unverified='Nordkap Carworks Rotterdam' -> flagged; pending='Hafenblick
           Automobile Munich' -> flagged; verified='Ostkreuz Motors Berlin' -> not flagged;
           payee(None) -> None
  13.8   PASS     gate 1 still green -- catalogue counts and correlations unchanged
           scripts.gate_phase1 exits 0 -- 10 passed, 0 failed, 0 pending
------------------------------------------------------------------------------
  8 passed, 0 failed, 0 pending
  GATE 13 GREEN
==============================================================================
```

### What shipped

| Area | Files |
|---|---|
| Dealer domain | `src/domain/dealer.py` — `Dealer`, `VerificationStatus`, `PayeeIdentity` (+ `needs_flag`/`one_line`), `dealer_uuid` on its own namespace |
| Condition | `src/domain/enums.py` — `VehicleCondition` (`new`/`used`/`certified_pre_owned`, `is_used`, `has_manufacturer_warranty`) |
| Listing gains both | `src/domain/listing.py` — `dealer_id` (nullable) and `condition` (defaults `USED`) on `Listing` and `ListingSummary` |
| Directory generator | `src/adapters/catalogue/dealers.py` — seeded synthetic directory, country-aware addresses/phones/legal forms, `real_world_denylist()` derived from the live brand pool, `assert_no_real_world_collisions` |
| Catalogue wiring | `src/adapters/catalogue/generator.py` — `SOURCES`, `_pick_condition`, per-listing `aux` RNG, dealer assignment by city + marketplace |
| Search filter | `src/domain/marketplace.py` (`SearchQuery.conditions`), `src/adapters/filtering.py`, `src/adapters/db/store.py` — Python predicate and SQL clause kept in lockstep |
| Directory store | `src/adapters/dealer_store.py` (protocol, `InMemoryDealerDirectory.seeded()`, `resolve_payee`), `src/adapters/db/dealer_store.py` (`PostgresDealerDirectory`) |
| Schema | `migrations/versions/0004_dealers.py`, `DealerRow` + two `ListingRow` columns, `dealer_to_row`/`to_dealer` in `mapping.py` |
| Seeding | `scripts/seed_marketplace.py` — dealers upserted and flushed **before** listings, or the new FK rejects every row |
| Card attribution | `src/mcp/ui/compiler.py` (`CardVisual` + five props), `src/mcp/ui/catalog.py`, `web/src/a2ui/catalog.tsx`, `src/mcp/ui/tools.py`, `src/mcp/ui/server.py` |
| Wiring | `src/agent/orchestrator.py`, `src/agent/demo_stream.py`, `src/api/main.py` (`build_dealer_directory`, `app.state.dealers`) |
| Gate | `scripts/gate_phase13.py`, `web/tests/dealer-card.spec.ts`, `web/playwright.dealer.config.ts`, `scripts/export_ui_fixtures.py` (real dealers in the golden fixture) |
| Tests | `tests/unit/test_domain_dealer.py` (21), `tests/unit/test_adapters_dealers.py` (25) |

Three things surfaced while building this that were not in the plan:

- **The first version rewrote the whole catalogue.** Drawing `dealer_id` and `condition` from
  the main generator RNG consumed two extra values per listing, which shifted every
  subsequent draw — so adding a dealer changed which *cars* the generator produced, and
  `test_every_car_the_demo_script_surfaces_has_its_own_model` went red because thirteen
  models with no hand-built 3D asset had wandered into the demo's results. Fixed by seeding a
  per-listing `random.Random(f"p13:{source}:{source_id}")`, which keeps both new fields
  deterministic while leaving every pre-P13 field bit-identical. **A new field must not
  retroactively change an old one** (DECISIONS.md D-072).
- **The directory's first run put "Via Artigiani 64, Berlin" in it** — an Italian street in a
  German city, from a single flat street pool. Two facts on one line contradicting each other
  is exactly the tell that stops a buyer believing the dealer is real, which is the whole
  value of dealer attribution. Streets are now keyed by country.
- **Gate 13.5 failed on a wrong query parameter**, not on the feature: `harness.html` wants
  `?fixture=results.json` (with the extension) and the spec asked for `?fixture=results`,
  which 404s silently and renders nothing. The failure looked exactly like "the props never
  reached the card" — worth remembering the next time a harness-driven criterion goes red.

### Deferred, deliberately

- **`[SCALE]` A real dealer-directory scraper.** Gated on a ToS/`robots.txt` check by whoever
  owns it, weekly cadence, never against an OEM-branded page without sign-off (PLAN-01 §0
  decision 1). The synthetic generator is **not** a placeholder for this — it is the permanent
  demo and dev data source.
- **`listings.dealer_id` stays nullable.** The assignment is decided by the generator, not by
  anything SQL can recompute, so there is no honest in-migration backfill; `python -m
  scripts.seed_marketplace` fills it (and the compose `command` already seeds on start).
  Gate 13.1 asserts zero orphans in a freshly generated catalogue, which is the property that
  actually matters.
- **`condition` does not yet influence ranking or TCO.** `DECISIONS.md` D-003's depreciation
  curve assumes new-car retention at year zero, which is now visibly an approximation for the
  197 `used` rows. Written down rather than silently left — making the curve condition-aware
  is P16's `[SCALE]` territory, not P13's.
- **Dealer attribution is on the results card only.** The detail surface and the booking form
  do not show it yet; the booking form is P14's job, where it becomes the payee disclosure.

---

## Phase 12 — Identity ✅

The first phase of `plans/PLAN-02-MARKETPLACE.md` (the two-sided build). Run on 2026-08-09
against live Postgres (`docker compose up -d postgres`, migration `0003_identity` applied) with
`--require-stack`, so 12.5 is a hard PASS rather than PENDING. 12.2 drives a real Chromium
against a scrubbed-environment backend on its own port (:8123), the same shape gates 7/8/11 use.

```
==============================================================================
GATE 12 -- IDENTITY -- accounts, roles, dummy OTP, profile capture
==============================================================================
  12.1   PASS     each demo OTP code authenticates a seeded account; a fourth code is rejected
           accepted ['123456', '234567', '345678']; rejected '999999' with 401
  12.2   PASS     demo-auth banner above the fold on /login; full sign-in works in a browser
           web/tests/auth.spec.ts passed against a real Chromium and a scrubbed-env backend
           on :8123 -- stats={'expected': 6, 'unexpected': 0, 'flaky': 0, 'skipped': 0}
  12.3   PASS     denylist scan: zero JWT libs, auth-provider SDKs or signing secrets
           116 files scanned across ('src', 'scripts', 'pyproject.toml', 'web/package.json',
           'web/package-lock.json') for 15 JWT/auth-provider/secret terms, 0 hits
  12.4   PASS     a buyer token cannot read a seller route; 403 not an accidental 404
           seller=200, buyer=403, anonymous=401 on GET /seller/profile
  12.5   PASS     account + profile survive process restart, every field intact
           account 509cc4c7..., profile and token all reloaded through a fresh store
           instance; exact income EUR 88,000.00 intact, band derived as '50k_100k'
  12.6   PASS     annual_income, income_band and phone are absent from every exported span
           6 attributes exported, 5 redaction markers (['account.email', 'account.phone',
           'profile.annual_income', 'profile.employer', 'profile.income_band']); raw
           phone/income/employer absent, tool.name untouched
  12.7   PASS     annual_income, income_band and employer reach zero model-facing payloads
           53 files scanned (src/agent, src/mcp, prompts/) for ['annual_income',
           'income_band', 'employer']; 0 references -- no prompt or tool result can carry them
  12.8   PASS     income_band is derived; no route can set it independently
           a body claiming '100k_plus' with no income resolved to 'undisclosed'; a body
           claiming 'under_25k' with EUR 120000 resolved to '100k_plus' -- derived, never
           accepted
  12.9   PASS     DEMO_MODE=true completes a login with no signup and no ANTHROPIC_API_KEY
           signed in and read /auth/me (role='buyer') with DEMO_MODE=true,
           ANTHROPIC_API_KEY and CARDINAL_DATABASE_URL both unset
  12.10  PASS     request-otp is honest about being a mock: banner + codes
           banner='DEMO AUTH — ANY CODE BELOW WORKS, NOT REAL SECURITY',
           demo_codes=['123456', '234567', '345678']
  12.11  PENDING  [SCALE] OTP attempt rate limiting
           rate limiting on OTP attempts not built -- [SCALE] (PLAN-02 P12); the demo codes
           are public by design, so throttling guesses protects nothing yet
------------------------------------------------------------------------------
  10 passed, 0 failed, 1 pending
  GATE 12 GREEN (with 1 pending)
==============================================================================
```

Without a database up, 12.5 reports `PENDING` (same convention as 1.10/3.2/4.1); without
`web/node_modules` + Chromium, 12.2 does (same convention as 6.2).

#### Extended 2026-08-09 — Sign in with Google

Added after the phase closed, so the gate was re-run rather than assumed. Re-run without a
database (Docker was unavailable on this machine), so 12.5 drops to `PENDING` by the
convention above — it was a hard PASS in the run pasted above and nothing in this change
touches persistence. 12.2 drove a real Chromium and now covers **8** browser assertions — the
new one asserts that a deployment with no Google credentials shows no Google button and can
still sign in by email, which is the environment a judge on a clean machine actually gets.

```
  12.1   PASS     each demo OTP code authenticates a seeded account; a fourth code is rejected
  12.2   PASS     demo-auth banner above the fold on /login; full sign-in works in a browser
           stats={'expected': 8, 'unexpected': 0, 'flaky': 0, 'skipped': 0}
  12.3   PASS     denylist scan: zero JWT libs, auth-provider SDKs or signing secrets
  12.4   PASS     a buyer token cannot read a seller route; 403 not an accidental 404
  12.5   PENDING  CARDINAL_DATABASE_URL unset -- no Postgres on this run
  12.6   PASS     annual_income, income_band and phone absent from every exported span
  12.7   PASS     annual_income, income_band and employer reach zero model-facing payloads
  12.8   PASS     income_band is derived; no route can set it independently
  12.9   PASS     DEMO_MODE=true completes a login with no signup and no ANTHROPIC_API_KEY
  12.10  PASS     request-otp is honest about being a mock: banner + codes
  12.11  PENDING  [SCALE] OTP attempt rate limiting
------------------------------------------------------------------------------
  9 passed, 0 failed, 2 pending
  GATE 12 GREEN (with 2 pending)
```

18 new tests in `tests/integration/test_api_auth_google.py`; suite total **880 passed, 64
skipped**. Google itself is never called — `exchange_code`/`fetch_identity` are stubbed, so
what is asserted is Cardinal's half: the CSRF state check (four ways to fail it), that the
role rides in the httpOnly cookie rather than the query string, and where each role lands.

Three things worth carrying forward, all recorded in D-087:

- **12.3 caught a docstring.** The denylist scans for auth-provider SDK names as plain
  strings, so *naming* a vendor in a comment turns the gate red. Left blunt on purpose; the
  comment now describes those vendors instead of naming them.
- **A real 500 on the happy path**, found by the new tests rather than by a judge: the
  callback passed `city=""` into `BuyerProfile`, which requires `min_length=1`. `city` and
  `country` are now `str | None` — `None` means *not stated*, which is what a Google sign-in
  actually knows, while `""` is still refused so the signup form cannot write a blank.
- **A new `/login` state**: a Google seller has no dealership (Google carries none), so they
  land on `/login?claim=dealership`. `LoginRoute`'s redirect has one exception for exactly
  that combination — checked against the account, not just the URL.

#### Fixed the same day — the test suite could hang instead of skipping

`make test` with no Postgres reachable **hung indefinitely** rather than skipping.
`pytest.mark.postgres` selects; it does not skip — the skip lives in the
`database_url_or_skip` fixture, and `test_adapters_cart_store_postgres.py` and
`test_adapters_lead_store_postgres.py` were marked but never requested it. They blocked
inside the driver's connect, stopping the run with no indication of which test held it. Both
now request it. The full suite went from **>600s and never finishing** to **7.8s**.

### What shipped

| Area | Files |
|---|---|
| Identity domain | `src/domain/identity.py` — `AccountRole`, `CustomerType`, `IncomeBand`, `band_for_income`, `Account`, `BuyerProfile` (with `income_band` as a `computed_field`), `SellerProfile`, `AuthToken`, `DEMO_OTP_CODES`, `DEMO_AUTH_BANNER`, `is_demo_otp` |
| Stores | `src/adapters/identity_store.py` (`AccountStore` protocol, `InMemoryAccountStore`, `OtpChallenge`, `build_account`/`build_profile`, token minting), `src/adapters/db/identity_store.py` (`PostgresAccountStore`) |
| Schema | `migrations/versions/0003_identity.py` — `accounts` (`UNIQUE (email, role)`), `account_profiles` (dual-storage `canonical`), `auth_tokens`, `otp_challenges`; four new rows in `src/adapters/db/models.py` |
| Auth transport | `src/api/auth.py` — `POST /auth/request-otp`, `POST /auth/verify-otp`, `GET /auth/me`, `POST /auth/logout`, `GET /seller/profile`; `current_account`/`require_role` as the one authorisation path |
| App wiring | `src/api/main.py` — `build_account_store`, `app.state.account_store`, `app.include_router(auth_router)` |
| PII redaction | `src/agent/tracing.py` — `income`/`salary`/`employer` added to `_PII_KEY_RE`; key-shaped matches now redact non-string values too |
| Frontend router | `web/src/main.tsx` (BrowserRouter + SessionProvider), `web/src/routes.tsx`, `web/src/auth/{api.ts,SessionContext.tsx,LoginPage.tsx}`, `web/src/styles.css` (+P12 block), `react-router-dom@7` |
| Proxy config | `web/vite.config.ts` and `web/nginx.conf` — `/auth/` prefix + `= /seller/profile` exact match, added in the same change (D-057's trap) |
| Gate | `scripts/gate_phase12.py`, `web/tests/auth.spec.ts`, `web/playwright.auth.config.ts` |
| Tests | `tests/unit/test_domain_identity.py` (39), `tests/unit/test_adapters_identity_store.py` (28), `tests/integration/test_api_auth.py` (18), `tests/integration/test_adapters_identity_store_postgres.py` (9) |
| Google sign-in *(added 2026-08-09)* | `src/adapters/oauth/google.py` — authorization-code flow, `GoogleIdentity`, `is_configured`/`new_state`/`authorization_url`/`exchange_code`/`fetch_identity`. No JWT library: the access token goes to Google's `userinfo` endpoint rather than verifying the `id_token` locally, which is what keeps gate 12.3 green |
| …routes | `GET /auth/providers`, `GET /auth/google/start`, `GET /auth/google/callback`, `POST /auth/claim-dealership` in `src/api/auth.py`; `sign_in_external`/`claim_dealership`/`get_seller_profile` on both `AccountStore` implementations |
| …web | `fetchProviders`/`startGoogle`/`claimDealership`/`needsDealership` in `web/src/auth/api.ts`; "Continue with Google" + the dealership claim screen in `web/src/auth/LoginPage.tsx`; the one `LoginRoute` exception in `web/src/routes.tsx`; `.google-button`/`.auth-divider` in `web/src/styles.css` |
| …tests | `tests/integration/test_api_auth_google.py` (18) |

`income_band` is a pydantic `computed_field`, not a stored column or a settable field — there is
no setter and no `model_validate` input for it, so gate 12.8 holds by construction rather than by
a check someone has to remember to write. A request body claiming a band it hasn't earned is
dropped at the model boundary, at `build_profile`, and again on reload from `canonical`.

Two things surfaced while building this that were not in the plan:

- **SQLAlchemy emitted the `account_profiles` INSERT before `accounts`.** The two tables are
  joined by a plain `ForeignKey` with no `relationship()` between the mappers, so the unit of
  work had no dependency edge to sort by and the FK rejected it. Caught by the Postgres
  integration suite on its first run (8 of 9 tests red), fixed with an explicit
  `await session.flush()` between the two adds rather than by declaring a relationship purely
  to fix ordering.
- **`/` must not be auth-guarded.** The first draft of `web/src/routes.tsx` wrapped the buyer
  chat in `RequireRole`. That would have turned gates 6.2, 7.x and 11.3 red — all three drive
  the real product at `/` with no session — and it would have demanded a signup before the agent
  says a word. Identity is required at *checkout* (P14), which is where it means something.
  The decision is recorded in `routes.tsx`'s own docstring and asserted by `auth.spec.ts`.

### Deferred, deliberately

- **`[SCALE]` OTP attempt rate limiting** — gate 12.11. The demo codes are public by design, so
  throttling guesses protects nothing until real OTP delivery exists to protect.
- **`[SCALE]` Real OTP delivery, passwords/passkeys, real sessions.** The `AccountStore`
  protocol is the seam; `verify_otp` is the one method a real verifier replaces.
- **`[SCALE]` Multi-tenancy.** Still gate 10.6's problem; no `tenant_id` anywhere.
- **Buyer-header session display and a sign-out control on `/`.** `SessionProvider` is mounted
  above the router and `App` can read it, but the chat rail does not surface the account yet —
  P14 adds the header alongside the cart icon, which is where it belongs visually.

---

## Phase 1 — Inventory ✅

Run on 2026-08-07 with the stack up (`docker compose up`), against Postgres 16 + pgvector.

```
==============================================================================
GATE 1 -- Inventory -- adapter protocol, seeded catalogue, structured search
==============================================================================
  1.1    PASS     >=100 listings (target 240)
           240 listings generated
  1.2    PASS     >=10 distinct categories (target 12)
           12 categories: convertible, coupe, crossover, electric, hatchback, luxury,
           pickup, sedan, sports, suv, van_mpv, wagon
  1.3    PASS     >=10 distinct brands within EVERY category
           ok  convertible  12 brands
           ok  coupe        12 brands
           ok  crossover    14 brands
           ok  electric     11 brands
           ok  hatchback    12 brands
           ok  luxury       12 brands
           ok  pickup       13 brands
           ok  sedan        12 brands
           ok  sports       12 brands
           ok  suv          12 brands
           ok  van_mpv      12 brands
           ok  wagon        12 brands
  1.4    PASS     both rent and buy present, each >=40
           buyable=150 rentable=110 (buy=130 rent=90 both=20)
  1.5    PASS     adapter contract suite passes against every adapter
           60 passed, 3 skipped in 0.10s
           parametrised over: mock_autobazaar, mock_drivenow
  1.6    PASS     two seed runs with the same seed are byte-identical
           sha256 54919b48db4cd9352ef3af816466db9e... identical across two processes
  1.7    PASS     every Listing validates; raw non-empty on all rows
           240/240 rows validate and round-trip; raw non-empty
  1.8    PASS     price/mileage/year correlation holds (no listing >2 sigma)
           max |z| = 1.731 (limit 2.0) on AB-1073 2019 Peugeot 2008
           pearson r(actual, model) = 0.9981 across 240 rows
  1.9    PASS     search returns summaries only, <=200 tokens each
           max summary 117 tokens, mean 105.3 (cap 200); a full record would be ~435 tokens
  1.10   PASS     docker compose up -> /health 200 with a listing count
           200 OK from http://localhost:8000/health
           backend=postgres listings=240 sources={'mock_autobazaar': 130, 'mock_drivenow': 110}
------------------------------------------------------------------------------
  10 passed, 0 failed, 0 pending
  GATE 1 GREEN
==============================================================================
```

Criterion 1.10 reports `PENDING` rather than `PASS` when no stack is running, so `make verify` works
on a machine with no Docker. Run `python -m scripts.gate_phase1 --require-stack` to make it a hard
failure, which is how the output above was produced.

### What shipped

| Area | Files |
|---|---|
| Adapter protocol | `src/adapters/protocol.py`, `src/adapters/registry.py` |
| Mock marketplaces | `src/adapters/mock/{base,drivenow,autobazaar}.py` |
| Catalogue generator | `src/adapters/catalogue/{taxonomy,generator}.py` |
| Retrieval semantics | `src/adapters/filtering.py`, `src/adapters/store.py` |
| Postgres | `src/adapters/db/*`, `migrations/versions/0001_initial_schema.py` |
| Seed | `scripts/seed_marketplace.py` |
| Transport | `src/api/main.py` (`/health`, `/adapters`), `Dockerfile`, `docker-compose.yml` |
| Tests | `tests/contract/` (60), `tests/unit/` (63), `tests/integration/` (26) |

`MockDriveNow` carries all 90 `rent` plus all 20 `both` listings; `MockAutoBazaar` carries the 130
`buy`. A rental marketplace that also sells its ex-fleet cars is a real business model, and it puts
every dual-offer listing on the adapter whose `availability` actually means something.

### Deferred, deliberately

- **`[SCALE]` pgvector semantic search.** The `listing_vectors` table and the `vector(768)` column
  exist and the extension is enabled; nothing writes embeddings. Structured search alone is enough
  for the hackathon (PHASE-1 §8), and enabling this later is a backfill, not a migration.
- **`[SCALE]` freshness/TTL and the staleness sweep.** `withdrawn_at` exists and every query
  excludes withdrawn rows; no sweep writes it yet.
- **`[SCALE]` a real adapter behind a feature flag.**

---

## Phase 2 — MCP ✅

Run on 2026-08-08, no container needed — every criterion is pure Python against an in-memory
catalogue plus a subprocess for the stdio checks.

```
==============================================================================
GATE 2 -- MCP -- Tool protocol layer, three servers, registry manifest
==============================================================================
  2.1    PASS     MCP Inspector connects to marketplace-mcp over stdio and lists all five tools
           connected over stdio, tools/list -> ['check_availability', 'compare_listings', 'get_listing', 'get_quote', 'search_cars']
  2.2    PASS     every tool description >=3 sentences with an explicit "call this when" clause
           14/14 tools carry a >=3-sentence prescriptive description
  2.3    PASS     every input schema sets additionalProperties: false and strict: true
           14/14 schemas set additionalProperties=false, strict=true
  2.4    PASS     search_cars result for the broadest query is <=20 items, <=4000 tokens
           20 items, total=240, 2338 tokens (cap 4000)
  2.5    PASS     get_listing result is <=800 tokens
           327 tokens (cap 800)
  2.6    PASS     confirm_booking is absent from the tool list presented to the model
           model-facing booking-mcp resolves to ('open_booking_form', 'open_checkout') (no confirm_booking, no submit_booking_draft)
           app-facing booking-mcp resolves to ('open_booking_form', 'open_checkout', 'submit_booking_draft', 'confirm_booking') (both present) -- resolved via the SDK's own Server.request_handlers, not read from config
  2.7    PASS     in-process and stdio builds of marketplace-mcp return byte-identical results
           identical 2417-byte result for {'categories': ['suv'], 'sort': 'price_asc', 'page_size': 5} across both transports
  2.8    PENDING  [SCALE] registry manifest validates against the registry schema
           not built -- marketplace-mcp registry submission is [SCALE] (PHASE-2 §7)
------------------------------------------------------------------------------
  7 passed, 0 failed, 1 pending
  GATE 2 GREEN (with 1 pending)
==============================================================================
```

Criterion 2.1 talks to the standalone stdio server over the real MCP JSON-RPC wire protocol via
`mcp.client.stdio` -- the programmatic equivalent of what MCP Inspector's UI does, since Inspector
itself has no CLI mode to script in CI. Criterion 2.6 is asserted the way PHASE-2 §8 insists on:
against the SDK's own `Server.request_handlers[ListToolsRequest]`, not against this project's own
`audience` bookkeeping read back to itself.

### What shipped

| Area | Files |
|---|---|
| Visibility mechanism | `src/mcp/audience.py` (`ToolSpec`, `for_audience`, `resolved_tool_names`) |
| Schema helper | `src/mcp/schema.py` (`strict_schema`, `enum_property`, `enum_array_property`) |
| `marketplace-mcp` | `src/mcp/marketplace/{tools,server,stdio}.py` -- 5 tools, real handlers over P1's `ListingStore`/adapters, in-process + stdio |
| `ui-mcp` | `src/mcp/ui/{tools,server}.py` -- 5 tools, schemas frozen, handlers stub to a labelled P6 non-implementation |
| `booking-mcp` | `src/mcp/booking/{tools,server,http}.py` -- 4 tools, schemas frozen, handlers stub to a labelled P7/P8 non-implementation; `confirm_booking` and `submit_booking_draft` carry `audience=("app",)` |
| Gate | `scripts/gate_phase2.py` |
| Tests | `tests/unit/test_mcp_{marketplace,ui,booking,audience}.py` (25) |

`search_cars` and `compare_listings` query across every registered marketplace at once via
`ListingStore.query(sources=registered_source_names())` rather than one adapter at a time -- the
model never learns marketplaces are plural, per CONSTITUTION II.6. `check_availability` and
`get_quote` route through `adapter_by_name` once a `source` is known, since pricing and booking
logic are genuinely adapter-specific.

`confirm_booking`'s invisibility (CONSTITUTION I.2) is enforced by construction, not by a
permission check: `audience=("app",)` means it is never passed into `create_sdk_mcp_server` when
building the model-facing `booking-mcp` config, so there is no tool for a permission callback to
guard in the first place. The same tool is fully present and callable on an `audience="app"`
build, proving the absence is deliberate rather than an unfinished implementation.

### Deferred, deliberately

- **`[SCALE]` Official MCP Registry manifest + submission (gate 2.8).** `marketplace-mcp`'s
  standalone stdio transport works today (gates 2.1, 2.7); writing and submitting the manifest is
  PHASE-2 §7's explicit `[SCALE]` line.
- **`[SCALE]` tool-level auth scopes for multi-tenant use.**
- **`booking-mcp`'s HTTP transport (`src/mcp/booking/http.py`) is wired but unexercised by any
  gate.** No `ui://` resource exists to serve yet -- that is P7's job. The module builds a real
  `StreamableHTTPSessionManager`-backed Starlette app today so P7 has a working transport to attach
  resources to rather than a transport to invent.

---

## Phase 3 — Agent ✅

Run on 2026-08-08 against live Postgres (`docker compose up -d postgres`, migrations already at
head from Phase 1's run) with `--require-stack`, so 3.2 is a hard PASS rather than PENDING.

```
==============================================================================
GATE 3 -- AGENT -- Orchestration, phase machine, subagents, demo mode
==============================================================================
  3.1    PASS     10 scripted personas each reach a complete RequirementProfile within budget
           Efficient Erik: complete in 1 turn(s)
           Renting Rita: complete in 3 turn(s)
           Family Fatima: complete in 4 turn(s)
           Sports Sam: complete in 2 turn(s)
           Electric Emma: complete in 3 turn(s)
           Wagon Will: complete in 4 turn(s)
           Luxury Liam: complete in 1 turn(s)
           Pickup Priya: complete in 3 turn(s)
           Convertible Carlos: complete in 3 turn(s)
           City Chloe: complete in 3 turn(s)
  3.2    PASS     a session survives process restart: resume by session_id recovers state exactly
           save -> load through a fresh store instance recovered phase + profile exactly
  3.3    PASS     DEMO_MODE=true completes the full flow with ANTHROPIC_API_KEY unset
           persona 'Efficient Erik' reached transact (booking_status='draft_submitted') with no ANTHROPIC_API_KEY set
  3.4    PASS     both researcher subagents appear in the trace with overlapping timestamps
           2 researchers, overlapping spans: mock_autobazaar=[36953.9439, 36953.9728], mock_drivenow=[36953.9439, 36953.9729]
  3.5    PASS     a backward transition mid-RECOMMEND returns to RESEARCH and re-ranks
           'Efficient Erik' + 'Actually, make it under 15000 euros' mid-RECOMMEND -> RESEARCH visited 2x; final phase transact
  3.6    PASS     every tool call appears in the PreToolUse audit log with session, turn, args hash
           4 tool calls audited, each with session id, turn, sha256 args hash
  3.7    PASS     prompts/ is the only source of prompt text -- no src/ literal exceeds 200 chars
           6 prompt files: critic.md, explainer.md, interviewer.md, orchestrator_system.md, researcher.md, slot_extraction.md; no long literal in src/
  3.8    PASS     interview never emits a search before >=2 slots are filled (over the 10 personas)
           10/10 personas: search_gate never had to deny a search_cars call (see tests/unit/test_agent_guardrails.py for the gate denying an under-filled profile directly)
------------------------------------------------------------------------------
  8 passed, 0 failed, 0 pending
  GATE 3 GREEN
==============================================================================
```

Without a database up, 3.2 reports `PENDING` rather than `PASS` (same convention as 1.10) — run
`python -m scripts.gate_phase3 --require-stack` to make it a hard failure.

Every other criterion runs with **no `ANTHROPIC_API_KEY` and no live `ClaudeSDKClient` session** —
see DECISIONS.md D-015 for why the gate is built entirely on `DEMO_MODE`'s deterministic path
rather than a live subprocess against the `claude` CLI, the same reasoning D-012 already
established for gate 2.6.

### What shipped

| Area | Files |
|---|---|
| Phase machine | `src/agent/phase_machine.py` — `Phase`, `SessionState`, turn budgets, exit predicates, `apply_profile_update`'s backward transition |
| Slot extraction | `src/agent/extraction.py` — `DemoSlotExtractor` (regex/keyword, offline) and `ModelSlotExtractor` (`claude-haiku-4-5`, live) behind one `SlotExtractor` protocol |
| Turn processing | `src/agent/interview.py` — the one `process_turn` both `demo.py` and `orchestrator.py` call through |
| Concurrent research | `src/agent/research.py` — `dispatch_researchers` fans out over `registered_source_names()` via `asyncio.gather` against the real `ListingStore` |
| Guardrails | `src/agent/guardrails.py` — `PreToolUse` audit hook (`AuditLog`, gate 3.6) + `can_use_tool` search-gate (gate 3.8) |
| Subagent roster | `src/agent/subagents.py` — `interviewer`/`researcher`/`critic`/`explainer` `AgentDefinition`s, prompts loaded from `prompts/` |
| Session durability | `src/agent/session_store.py` — `PostgresSessionStateStore` (reuses P0's `sessions` table, D-014) + `InMemorySessionStateStore` |
| Demo mode | `src/agent/demo.py` — `run_demo_session`, the full INTERVIEW→RESEARCH→RECOMMEND→TRANSACT flow with no SDK involved |
| Live orchestration | `src/agent/orchestrator.py` — real `ClaudeAgentOptions` wiring (`mcp_servers`, `agents`, `hooks`, `can_use_tool`, model routing); gate-unexercised by design (D-015) |
| Prompts | `prompts/{orchestrator_system,interviewer,researcher,critic,explainer,slot_extraction}.md` |
| Gate | `scripts/gate_phase3.py` |
| Fixtures | `tests/fixtures/demo/personas.json` — 10 scripted personas |
| Tests | `tests/unit/test_agent_{phase_machine,extraction,guardrails,demo,prompts}.py` (66), `tests/integration/test_agent_session_store_postgres.py` (4) |

`src/agent` joined `tests/test_layer_boundary.py`'s `REQUIRED_LAYERS` (alongside `mcp`, which had
been live since P2 but wasn't added at the time). The Makefile's `typecheck` target now runs
`mypy src/agent` separately from `mypy --strict src/domain` rather than folding both under one
`--strict` invocation — `src/agent` legitimately imports `src/adapters`, and a combined `--strict`
call was transitively strict-checking (and failing on) not-yet-strict adapters code it followed
through that import. `src/agent` is held to the same bar via pyproject's per-module override
instead.

### Deferred, deliberately

- **`[SCALE]` Interrupt / steering mid-turn.**
- **`[SCALE]` Compaction strategy for very long sessions.**
- **`[SCALE]` Multi-provider fallback when the primary API rate-limits.**
- **A live rehearsal of `orchestrator.py` against the real `claude` CLI.** The wiring is real,
  type-checked and imports cleanly; nobody has yet run it end-to-end with a live model. PHASE-3 §7
  says to rehearse `DEMO_MODE` at least once before a real demo, not the live path, but a live
  rehearsal is still worth doing before this is called demo-ready in the fuller sense.

---

## Phase 4 — Memory (partial)

Run on 2026-08-08 against live Postgres (`docker compose up -d postgres`) with `--require-stack`,
so 4.1 is a hard PASS rather than PENDING.

```
==============================================================================
GATE 4 -- MEMORY -- Four tiers, consolidation, drift, forget-me
==============================================================================
  4.1    PASS     profile survives process restart; every slot's confidence/source_turn intact
           save -> load through a fresh store instance kept every slot's confidence and source_turn
  4.2    PASS     a locked slot is not modified by a later low-confidence inference
           turn-1 locked budget (EUR 28000) survived a turn-9 confidence-0.4 inference of EUR 45000 unchanged; the unlocked category slot in the same turn did update
  4.3    PASS     journal answers 'why rank A over B' from a recorded row, zero model calls
           explain() returned the recorded rationale for 'mock_autobazaar:AB-1034' byte-identical to the row `_record_recommendation` wrote, with ANTHROPIC_API_KEY unset (604 chars, inputs_hash=25a4d431be97...)
  4.4    PENDING  [SCALE] second session for a known user recalls >=1 prior constraint unprompted
           episodic memory (remember/recall tool, MEMORY.md index) not built -- [SCALE]
  4.5    PENDING  [SCALE] contradicting memory sets superseded_by; recall returns the newer
           contradiction handling over MemoryRecord.superseded_by not built -- [SCALE]
  4.6    PENDING  [SCALE] memory index for 50 memories is <=800 tokens
           MEMORY.md-style progressive-disclosure index not built -- [SCALE]
  4.7    PENDING  [SCALE] drift detector fires on a scripted divergence, asks a question
           preference-drift detector over the interaction log not built -- [SCALE]
  4.8    PENDING  [SCALE] forget_me leaves zero rows across all four stores + Langfuse
           forget_me erasure path not built -- [SCALE]; Langfuse itself is P9's
------------------------------------------------------------------------------
  3 passed, 0 failed, 5 pending
  GATE 4 GREEN (with 5 pending)
==============================================================================
```

Without a database up, 4.1 reports `PENDING` rather than `PASS` (same convention as 1.10/3.2) --
run `python -m scripts.gate_phase4 --require-stack` to make it a hard failure. 4.2 and 4.3 are pure
Python and always run regardless of the stack.

Built now, ahead of PLAN-00 §4's suggested backfill-last order, because P4's `[MVP]` scope only
needs P0 (`RequirementProfile`) and P3 (`SessionState`, turn processing) -- both already green --
and CONSTITUTION III.2 blocks starting a phase before the *previous* one's gate is green, not
building phases out of the suggested shipping sequence. See DECISIONS.md D-019.

### What shipped

| Area | Files |
|---|---|
| Decision journal | `src/agent/journal.py` -- `DecisionJournal` protocol, `InMemoryDecisionJournal`, `PostgresDecisionJournal` (reuses the `decisions` table P0 pre-created), `explain()`, `compute_inputs_hash()`, `session_uuid()` |
| Journal wired into RECOMMEND | `src/agent/demo.py`'s `_record_recommendation` writes one `DecisionEntry` per recommendation, with a rationale honest about P3's placeholder pick logic (D-019) |
| Gate | `scripts/gate_phase4.py` |
| Tests | `tests/unit/test_agent_journal.py` (13, includes domain-level locked-slot coverage), `tests/integration/test_agent_journal_postgres.py` (4) |

Working state (4.1, 4.2) needed no new production code: `RequirementProfile`/`Slot.fill`'s
locked-slot guard is P0's, and `PostgresSessionStateStore`'s restart-resume is P3's (gate 3.2)
-- PHASE-4 §3.1 and PHASE-3 §8 gate 3.2 describe the same code-owned mechanism from two angles on
purpose. Gate 4.1/4.2 assert it explicitly under the Phase 4 label rather than silently relying on
Phase 3 having already proven it.

### Deferred, deliberately

- **`[SCALE]` Episodic memory** (`remember`/`recall` tool, markdown + frontmatter, `MEMORY.md`
  index) -- gate 4.4, 4.6.
- **`[SCALE]` Semantic retrieval** over listings and past decisions (pgvector) -- not gated
  directly, but a prerequisite PLAN-00 §4 also defers.
- **`[SCALE]` Consolidation, contradiction detection (`MemoryRecord.superseded_by`), staleness
  sweep** -- gate 4.5.
- **`[SCALE]` Preference-drift detection** -- gate 4.7.
- **`[SCALE]` `forget_me` erasure** across all four stores + Langfuse -- gate 4.8. `MemoryRow`
  exists in the schema (P0/P1) but nothing writes to it yet, so there is nothing to erase from
  that store today; the other three (`decisions`, `sessions`, vectors) would need the same
  treatment once P9's Langfuse integration exists to erase from too.

---

## Phase 5 — Reasoning ✅

Run on 2026-08-08, no container needed — every criterion is pure/deterministic code
(CONSTITUTION II.2), the same reasoning D-015 already established for gate 3.

```
==============================================================================
GATE 5 -- REASONING -- scoring, TCO, grounding, critic pass
==============================================================================
  5.1    PASS     Determinism: same profile + seed, two runs, byte-identical
           15 candidates ranked, byte-identical across two runs
  5.2    PASS     ScoreBreakdown contributions sum to the total within 1e-9
           total=0.690000, sum(contributions)=0.690000
  5.3    PASS     Hard filters remove rows -- no filtered listing appears at any rank
           96000 km listing excluded by a lte-80000 hard filter; 1/2 candidates survived
  5.4    PASS     Golden set of 20 personas: precision@3 >= 0.8 vs stated constraints
           19/20 personas feasible, 1 infeasible (a real answer, not a missing one); mean
           precision@3=1.000; worst persona 'Golden 01 - Budget Hatchback Buyer'
           precision@3=1.00
  5.5    PASS     Groundedness validator rejects a deliberately fabricated statistic
           999% fabricated claim rejected; genuine 80% claim (curve[0]=0.80) accepted
  5.6    PASS     TCO: break-even for a known fixture matches a hand-computed value
           break_even_month=5 (hand-derived from Buy(h)=370+543.25h, Rent(h)=631.25h);
           buy(5)=EUR 3086.25 (hand: 3086.25), rent(5)=EUR 3156.25 (hand: 3156.25), both
           within EUR 50
  5.7    PASS     Rental pricing tiers applied -- weekly rate != daily x 7 in output
           rental line = EUR 500.00 (the monthly tier), not daily x 30 = EUR 750.00; weekly
           tier EUR 140.00 != daily x 7 = EUR 175.00
  5.8    PASS     Critic catches a seeded violation before render
           critic dropped 'LATE' (available 2026-11-01, after target 2026-09-15):
           fixture:LATE: available_from 2026-11-01 is after target_date 2026-09-15
  5.9    PASS     domain/scoring.py has zero imports outside stdlib + pydantic
           7 import root(s), all stdlib or pydantic: ['__future__', 'collections', 'enum',
           'pydantic', 're', 'typing', 'uuid']
  5.10   PENDING  [SCALE] Counterfactual solver returns >=2 relaxation options on a
                  zero-result query
           constraint relaxation / counterfactual solver (PHASE-5 §7) not built -- [SCALE]
------------------------------------------------------------------------------
  9 passed, 0 failed, 1 pending
  GATE 5 GREEN (with 1 pending)
==============================================================================
```

### What shipped

| Area | Files |
|---|---|
| Pure scoring math | `src/domain/scoring.py` — `Criterion` enum, `DEFAULT_WEIGHTS`, five `normalise_*` functions, `score_breakdown`, `ranking_sort_key`, `extract_numbers` (grounding). Zero imports outside stdlib + pydantic (gate 5.9) |
| Ranking engine | `src/domain/ranking.py` — `apply_hard_filters`, `score_listing`, `build_rationale`, `validate_grounding`/`finalize_rationale` (grounding), `rank`, `critic_pass`. The seam that reads real `Listing`/`RequirementProfile` and calls into `scoring.py`'s pure functions (D-020) |
| TCO engine | `src/domain/tco.py` — `residual_fraction_at_month`, `compute_buy_tco`, `compute_rent_tco`, `compute_comparison` (break-even solver), added to P0's existing `TcoEstimate`/`TcoComparison` contracts |
| Cost formulas | `src/domain/costs.py` — `monthly_insurance`/`monthly_energy`/`monthly_maintenance`/`monthly_running_cost`/`annual_road_tax`, shared by the `running_cost` scoring criterion and every recurring TCO line |
| Constants | `src/domain/constants.py` — every illustrative TCO/cost number in one place with a source comment (PHASE-5 §10's own risk mitigation) |
| Research fix | `src/agent/research.py` — `_query_from_profile` now sets `available_between` when `target_date` is known (D-023), so RESEARCH stops handing RECOMMEND candidates the critic would immediately reject |
| Demo wiring | `src/agent/demo.py` — RECOMMEND now calls `rank()` + `critic_pass()` instead of P3's "first surviving candidate" placeholder; records a `WEIGHTS_CHOSEN` and a real scored `RECOMMENDATION_MADE` `DecisionEntry` through P4's existing journal, unchanged schema (D-019's promise made good) |
| Gate | `scripts/gate_phase5.py` |
| Fixtures | `tests/fixtures/demo/golden_set.json` — 20 personas for gate 5.4, distinct from P3's 10 |
| Tests | `tests/unit/test_domain_{scoring,costs,tco,ranking}.py` (58), `tests/unit/helpers.py` (hand-built `Listing` factory) |

`domain/scoring.py` stays exactly what PHASE-5 §3 asks for — property-testable with no model,
no fixtures, no event loop — by keeping every normalisation function a pure function of
primitives; `domain/ranking.py` is the new seam that reads a real `Listing` and calls into it
(D-020). Hard filtering, budget, and the critic pass are three distinct, coexisting mechanisms
rather than one (D-022): a generic `HardFilter` removes a row outright (gate 5.3), a stated
budget instead scores a hard 0 on its own `budget_fit` criterion without necessarily removing
the row (the model's chosen weight decides how much that costs it), and the critic pass is a
second, independent check before anything reaches RECOMMEND.

### Deferred, deliberately

- **`[SCALE]` Constraint relaxation / counterfactuals on infeasibility** (PHASE-5 §7) — gate
  5.10. `SessionState.infeasible` (P3) still carries the flag forward honestly; nothing yet
  computes "raising the ceiling €2,000 opens seven" from it.
- **`[SCALE]` Calibration of weights against outcome data.**
- **`[SCALE]` Regional tax, insurance-band, and energy-price tables.** `src/domain/constants.py`
  is flat and illustrative by design (PHASE-5 §10); any UI rendering these figures must flag
  them as such.
- **A live rehearsal of the model actually choosing a `WeightSet`.** `rank()` takes whatever
  weights it's given (CONSTITUTION II.2); `DEMO_MODE` and the gates use `DEFAULT_WEIGHTS`
  because nothing in P5's scope wires a live session to emit its own — that's `orchestrator.py`
  calling `rank()` from inside a real `interviewer`/tool-call turn, still unexercised the same
  way D-015 leaves the rest of live orchestration unexercised until a real rehearsal happens.

---

## Phase 6 — Generative UI ✅

Run on 2026-08-08, no container needed for 6.1/6.3-6.7/6.9 (pure/deterministic Python, D-015's
reasoning); 6.2 needs `web/`'s npm dependencies and a Chromium build, both present on this
machine, so it ran as a hard PASS rather than PENDING.

```
==============================================================================
GATE 6 -- GENERATIVE-UI -- A2UI catalog, compiler, transport, escape hatch
==============================================================================
  6.1    PASS     Every message the compiler emits validates against the catalog schema
           6 compiled surfaces, 11 wire messages, 0 validation errors
  6.2    PASS     Golden-message fixtures render in a headless browser with zero console errors
           6 passed (web/tests/render.spec.ts, one test per golden fixture)
  6.3    PASS     compose_surface with an unknown component is rejected; the error reaches the
                  model as a tool result; nothing is forwarded to the renderer
           rejected as a tool result, nothing pushed to the sink: "compose_surface rejected:
           UNKNOWN_COMPONENT (root): 'NotInTheCatalog' is not in the registered catalog"
  6.4    PASS     compose_surface with a dangling child reference, a duplicate id, and depth > 8
                  are each rejected
           DANGLING_CHILD, DUPLICATE_ID, and DEPTH_EXCEEDED (depth 9 > 8) each independently
           rejected
  6.5    PASS     Action round-trip: a simulated click reaches the agent session with full
                  provenance
           provenance recorded in the session's action inbox: {'surface': 'gate65:results',
           'component': 'card-0', 'action': 'explain', 'payload': {'sourceId': 'AB-1'}}
  6.6    PASS     Surface identity is stable -- a second render_results in the same session
                  updates, does not recreate
           createSurface count stayed at 1 across two render_results calls
  6.7    PASS     All 8 powertrain GLBs are <=2 MB; total asset bundle <=16 MB
           8/8 archetypes present, largest 920 bytes (limit 2097152), total bundle 9426 bytes
           (limit 16777216)
  6.8    PASS     Every <model-viewer> has a poster; list contexts use reveal="interaction"
           1 <model-viewer> usage(s), all carry poster + reveal="interaction"
  6.9    PASS     All A2UI imports are from @a2ui/*/v0_9; exactly one module imports
                  MessageProcessor
           6 source files scanned, all @a2ui imports pinned to /v0_9; MessageProcessor imported
           only by web/src/a2ui/adapter.ts
  6.10   PENDING  [SCALE] Reduced-motion honoured; every interactive element has a visible focus
                  state
           reduced-motion + full a11y pass (PHASE-6 §7) not built -- [SCALE]
------------------------------------------------------------------------------
  9 passed, 0 failed, 1 pending
  GATE 6 GREEN (with 1 pending)
==============================================================================
```

Criterion 6.2 reports `PENDING` rather than `PASS` when `web/node_modules` hasn't been
installed (`npm install` + `npx playwright install chromium`, both inside `web/`), the same
convention gate 1.10/3.2/4.1 use for a heavy optional prerequisite.

### What shipped

| Area | Files |
|---|---|
| A2UI wire protocol | `src/mcp/ui/messages.py` — `createSurface`/`updateComponents`/`updateDataModel`/`deleteSurface`, built directly from `@a2ui/web_core`'s own `schemas/server_to_client.json` |
| Catalog registry (server-side) | `src/mcp/ui/catalog.py` — `ComponentSpec` for a minimal slice of `basicCatalog` plus all nine `carCatalog` components (PHASE-6 §3's table) |
| Escape-hatch validator | `src/mcp/ui/validate.py` — unknown component, missing/unknown prop, duplicate id, dangling child ref, cycle, depth > 8 (CONSTITUTION II.4) |
| Surface identity | `src/mcp/ui/surfaces.py` — `SurfaceRegistry`, deterministic `f"{session_id}:{kind}"` ids (gate 6.6) |
| Compiler | `src/mcp/ui/compiler.py` — `compile_{progress,results,detail,tco}_surface` (pure functions of each frozen P2 tool's args) + `compile_{score_breakdown,tco_breakdown}_surface` (direct, no-recomputation renders of real P5 `ScoreBreakdown`/`TcoComparison` objects, D-026) + `to_messages` (create-once-then-update, gate 6.6) |
| Action round-trip | `src/mcp/ui/actions.py` — `parse_action`/`to_user_turn`, `{surface, component, action, payload}` provenance (gate 6.5) |
| Transport | `src/mcp/ui/sink.py` — `UISink` protocol, `NullUISink` (tests/gates), `QueueUISink` (real, per-session `asyncio.Queue`) |
| `ui-mcp` real handlers | `src/mcp/ui/tools.py`, `src/mcp/ui/server.py` — P2's five frozen tool schemas now call the compiler and push through a session's `UISink` instead of returning a labelled stub |
| Live wiring | `src/agent/orchestrator.py` — per-session `SurfaceRegistry`/`QueueUISink`/action inbox, threaded into `build_ui_server` |
| SSE + actions transport | `src/api/main.py` — `GET /sessions/{id}/events` (SSE relay of a session's `QueueUISink`), `POST /sessions/{id}/actions` (action round-trip) |
| Frontend scaffold | `web/` — Vite + React 19, `@a2ui/react@0.9.1` + `@a2ui/web_core@0.9.1` pinned to `/v0_9`, one adapter module (`web/src/a2ui/adapter.ts`, gate 6.9), `carCatalog` component implementations (`web/src/a2ui/catalog.tsx`), chat rail + A2UI canvas (`web/src/App.tsx`) |
| PowertrainExplainer assets | `scripts/generate_powertrain_assets.py` — 8 hand-built placeholder glTF 2.0 binaries + PNG posters (D-028), `web/public/models/powertrain/*.{glb,png}` |
| Golden fixtures | `scripts/export_ui_fixtures.py` — exports real compiler output to `web/public/fixtures/*.json`; `web/harness.html` + `web/src/dev/fixture-harness.tsx` render one fixture through the real `MessageProcessor`/`carCatalog` |
| Headless-browser test | `web/tests/render.spec.ts` + `web/playwright.config.ts` — gate 6.2 |
| Gate | `scripts/gate_phase6.py` |
| Tests | `tests/unit/test_mcp_ui.py` (rewritten from P2's stub-pinning test), `tests/unit/test_ui_{validate,compiler,actions}.py`, `tests/integration/test_api_ui.py` |

`compile_results_surface`/`compile_progress_surface`/`compile_detail_surface`/`compile_tco_surface`
are pure functions of exactly what each frozen P2 tool schema carries — PHASE-6 §4's own
worked example ("`compile_results_surface(args)  # pure function, unit-tested`") holds
literally. `compile_score_breakdown_surface`/`compile_tco_breakdown_surface` are the "no
recomputation" counterparts PROGRESS.md's Phase 5 entry promised: they take P5's real
`ScoreBreakdown`/`TcoComparison` objects directly and map every field into props with no
second computation (D-026), reached by the action round-trip rather than a fresh model tool
call, since neither frozen schema carries per-criterion or per-line detail.

`CompareTable`, `Vehicle360`, and `RelaxationOptions` are registered in both catalogs
(server-side `src/mcp/ui/catalog.py` and client-side `web/src/a2ui/catalog.tsx`) so
`compose_surface` can validate and the renderer can draw a tree naming them, but the `[MVP]`
compiler never emits them itself — `CompareTable` because P2's five `ui-mcp` tools have no
dedicated comparison tool (PHASE-6 §4's escape hatch is the only path there today); `Vehicle360`
and `RelaxationOptions` because their `[SCALE]` prerequisites (real turntable imagery; PHASE-5
§7's counterfactual solver, gate 5.10) aren't built.

### Deferred, deliberately

- **`[SCALE]` `Vehicle360`** (image-sequence turntable of the actual vehicle) — PHASE-6 §5's
  own table marks this `[SCALE]`; every "3D per listing" surface still routes through
  `PowertrainExplainer`'s finite, category-level archetypes instead.
- **`[SCALE]` Progressive/streaming render as the agent composes.** Every surface renders in
  one `updateComponents` call today; PHASE-6 §2 lists streaming partial composition as
  `[SCALE]`.
- **`[SCALE]` Theme propagation, reduced-motion, full a11y pass** — gate 6.10.
- **Real `PowertrainExplainer` geometry.** The eight GLBs are hand-built placeholder unit
  cubes (D-028), honestly labelled "representative image" — real licensed or hand-modelled
  cutaways are a file swap under `web/public/models/powertrain/`, not a code change.
- **A live rehearsal of the model actually calling `render_results`/`compose_surface` inside a
  real session.** `src/agent/orchestrator.py`'s wiring is real and type-checked (per-session
  `SurfaceRegistry`/`QueueUISink`, threaded into `build_ui_server`), but — the same D-015
  reasoning gates 3/5's live paths — nothing has yet run it against the real `claude` CLI.
- **MCP App iframes.** PHASE-6 §2 explicitly puts this out of scope — different protocol,
  different trust boundary, P7's job.

---

## Phase 7 — MCP Apps ✅

Run on 2026-08-08, no container needed for the backend's own logic (in-memory catalogue) — the
ten criteria are Playwright-driven against a real running `src.api.main:app` and the `booking-mcp`
HTTP transport it lazily spawns, both started by the gate itself on a dedicated port (D-033).

```
==============================================================================
GATE 7 -- MCP-APPS -- Host implementation, sandbox, booking form
==============================================================================
  7.1    PASS     Inner iframe's origin != host origin (asserted from the browser, not from config)
           7.1 inner iframe origin != host origin, asserted from the browser
  7.2    PASS     CSP on the inner document matches the resource's _meta.ui.csp, defaults applied
           7.2 CSP on the inner document matches the resource's declared csp, defaults applied
  7.3    PASS     A fetch() to an undeclared domain from inside the App fails and is logged as blocked
           7.3 fetch() to an undeclared domain from inside the App fails and is logged as blocked
  7.4    PASS     ui/initialize completes; hostContext.theme reaches the App and visibly applies
           7.4 ui/initialize completes; hostContext.theme reaches the App and visibly applies
  7.5    PASS     ui/notifications/tool-input delivers pre-fill exactly once, after init
           7.5 ui/notifications/tool-input is delivered exactly once, after initialize responds
  7.6    PASS     tools/call from the view reaches the MCP server through the host proxy only
           7.6 tools/call from the view reaches the server only through the host proxy
  7.7    PASS     ui/resource-teardown removes the iframe/listeners; no leak after 20 cycles
           7.7 resource-teardown removes the iframe; no leak after 20 open/close cycles
  7.8    PASS     size-changed resizes the container without layout shift in the surrounding surface
           7.8 size-changed resizes the container without layout shift in the surrounding surface
  7.9    PASS     Audit log has one entry per view-initiated RPC, no gaps, for a full booking flow
           7.9 audit log has one entry per view-initiated RPC, no gaps, for a full booking flow
  7.10   PASS     The App renders and functions with JavaScript's network access fully blocked
           7.10 the App renders and functions with JavaScript's network access fully blocked
------------------------------------------------------------------------------
  10 passed, 0 failed, 0 pending
  GATE 7 GREEN
==============================================================================
```

Criterion 7.N reports `PENDING` instead of running when `web/node_modules`/Chromium aren't
installed, the same convention gate 6.2 uses; all ten collapse to that one prerequisite since a
single Playwright run (`web/tests/mcp-apps.spec.ts`) produces every criterion's evidence.

### What shipped

| Area | Files |
|---|---|
| Host-side plumbing (resource-agnostic) | `src/mcp/apps/{meta,audit,proxy}.py` — `DEFAULT_CSP`/`effective_csp`/`resource_ui_meta`, `AppAuditLog`, `call_view_rpc` (the one path from a view to any MCP server, D-031) |
| `ui://booking/form` resource | `src/mcp/booking/resources.py` — registered on `booking-mcp`'s own `Server` via `list_resources`/`read_resource`, independent of `create_sdk_mcp_server`'s tool-only wiring; `src/mcp/booking/static/booking_form.html` — the App itself, plain HTML/CSS/JS, no build step, no framework |
| Real tool handlers | `src/mcp/booking/tools.py` — `open_booking_form` pushes a `mcp_app_open` message through the session's `UISink` (D-032) instead of a stub; `submit_booking_draft` records a draft in an in-memory, id-keyed store; `open_checkout`/`confirm_booking` stay P8 stubs (out of scope, PHASE-7 §2) |
| Session-scoped booking server | `src/mcp/booking/server.py`, `src/agent/orchestrator.py` — `build_booking_server` now takes `session_id`/`sink` like `build_ui_server` already did |
| Host-proxy API | `src/api/main.py` — `POST /mcp-apps/{session_id}/rpc` (the only thing a browser ever calls; resources over real MCP-over-HTTP, tools in-process, D-031), `GET /mcp-apps/{session_id}/audit`, lazy loopback-only `booking-mcp` HTTP subprocess (`_ensure_booking_mcp_http`) |
| MCP host frontend | `web/src/mcp-host/{protocol,rpcChannel,hostBridge,sandboxOrigin,csp,outerEntry,sandboxProxyEntry,McpAppHost}.ts(x)` — the double-iframe handshake, RPC relay, and CSP injection; `web/mcp-outer.html` + `web/mcp-sandbox-proxy.html` are the two non-React entry points |
| Product wiring | `web/src/App.tsx` — mounts `McpAppHost` on an `mcp_app_open` SSE message, discriminated from a real A2UI message by the absence of A2UI's own `version` field; `web/src/styles.css` — the host panel as a fixed overlay, never reflowing the canvas (gate 7.8) |
| Gate-only harness | `web/mcp-host-harness.html` + `web/src/dev/mcp-host-harness.tsx` — mounts `McpAppHost` directly from query params, no live session, mirroring gate 6.2's `harness.html` pattern; exposes `window.__cardinalOpen`/`__cardinalClose` for gate 7.7's 20-cycle check |
| Gate | `scripts/gate_phase7.py`, `web/tests/mcp-apps.spec.ts`, `web/playwright.mcp-apps.config.ts` (kept separate from `playwright.config.ts` so gate 6 never depends on a Python backend) |
| Tests | `tests/unit/test_mcp_apps.py` (8), `tests/unit/test_mcp_booking.py` (+3 new, 7 total) |

The double-iframe (PHASE-7 §5.1) is four browsing contexts deep exactly as drawn: host page →
outer `<iframe src="/mcp-outer.html">` (same origin as host, the only thing that ever calls
`/mcp-apps/*/rpc`) → sandbox proxy `<iframe src="/mcp-sandbox-proxy.html">` (a genuinely
different origin in dev via D-030's `127.0.0.1`/`localhost` split, a dumb relay that never
interprets a forwarded message's contents) → inner `blob:` iframe (same origin as the proxy,
holding the actual resource HTML with a CSP `<meta>` tag injected ahead of it). The one thing
that cost real debugging time and is now D-034: a `blob:` document inherits its creator's CSP
*in addition to* its own declared one, enforced as an intersection — the sandbox proxy's shell
CSP has to be at least as permissive as any resource's effective CSP or it silently narrows it
back down, with no console error pointing at CSP as the cause.

`confirm_booking`/`open_checkout` remain reachable in principle through `/mcp-apps/*/rpc`'s
in-process `tools/call` path (nothing about the transport itself re-hides them, since
`RESOURCE_ROUTES`/`ALLOWED_VIEW_TOOLS` — not tool audience — is what gates a *view's* access) but
`ui://booking/form`'s own allowlist only names `submit_booking_draft`; calling either through
this endpoint today still hits P2's unimplemented stub either way. The real gesture-token check
CONSTITUTION I.2 requires for `confirm_booking` is P8's job, same as the tool's actual behaviour.

### Deferred, deliberately

- **`[SCALE]` `ui/request-display-mode` beyond acknowledging it.** The host answers every
  request with `{displayMode: "inline"}` regardless of what was asked (PHASE-7 §2 marks
  fullscreen/pip `[SCALE]`); the RPC plumbing exists so this is a body change, not new wiring.
- **`[SCALE]` Full theme/style-variable propagation.** `hostContext.styles.variables` carries two
  colour variables today, enough for gate 7.4's "visibly applies"; a richer variable set is a
  data change in `outerEntry.ts`'s `buildInitializeResult`, not a protocol change.
- **`[SCALE]` `ui/update-model-context`.** Acknowledged, not acted on — PHASE-7 §2's own
  `[SCALE]` line; there is no later-turn model context to update yet in this phase's scope.
- **Durable audit-log storage.** `AppAuditLog` is in-memory, one instance per process, the same
  posture gate 3.6's `AuditLog` has today. `[SCALE]` is Postgres; the entry shape doesn't change.
- **Connection pooling for the `resources/read` HTTP client.** `_read_resource_via_http` opens a
  fresh `mcp.client.streamable_http` session per call (D-031) — fine at this call volume, a
  persistent session is `[SCALE]` if that ever changes.
- **A live rehearsal of the model actually calling `open_booking_form` inside a real session.**
  `src/agent/orchestrator.py` wires `booking-mcp` with real `session_id`/`sink` now, type-checked
  and unit-tested (`tests/unit/test_mcp_booking.py`), but — the same D-015 reasoning already
  applied to gates 3/5/6's live paths — nobody has yet run it against the real `claude` CLI.
- **Checkout (`ui://checkout/payment`, `open_checkout`, `confirm_booking`'s real behaviour).**
  Explicitly out of this phase (PHASE-7 §2) — P8's job, and `src/mcp/apps/` was built
  resource-agnostic specifically so P8 is a second resource + a second `RESOURCE_ROUTES` entry,
  not a second host implementation.

---

## Phase 8 — Commerce ✅

Run on 2026-08-08, no container needed for 8.1/8.2/8.4/8.5/8.7/8.8/8.9/8.12 (pure/deterministic
Python, D-015's reasoning applied the same way gate 5 applied it to reasoning); 8.3/8.6/8.10/8.11
need `web/`'s npm dependencies and a Chromium build, both present on this machine, so they ran as
hard PASS rather than PENDING.

```
==============================================================================
GATE 8 -- COMMERCE -- Booking lifecycle, mock gateway, financing, idempotency
==============================================================================
  8.1    PASS     State machine: all (state, event) pairs either transition or explicitly reject
           42 (state, event) pairs checked over 7 states x 6 events: 6 transition, 36 explicitly
           reject
  8.2    PASS     confirm_booking is absent from the model's resolved toolset
           model-facing booking-mcp resolves to ('open_booking_form', 'open_checkout') (no
           confirm_booking) -- app-facing resolves to ('open_booking_form', 'open_checkout',
           'submit_booking_draft', 'mint_gesture_token', 'confirm_booking') (confirm_booking
           present) -- resolved via the SDK's own Server.request_handlers, not read from config
  8.3    PASS     No agent-driven path reaches confirm_booking -- zero calls without a real click
           8.3 no agent-driven path reaches confirm_booking or mint_gesture_token
  8.4    PASS     confirm_booking without a valid gesture_token is rejected
           rejected: 'confirm_booking rejected: gesture token is missing, unknown, or already used'
  8.5    PASS     Double-submit with the same idempotency key produces one booking, two identical
                  responses
           one booking (e0eea461-d447-4e90-9eb7-39f6645447a2), two identical responses:
           {'booking_id': 'e0eea461-d447-4e90-9eb7-39f6645447a2', 'state': 'confirmed', 'outcome':
           'success', 'message': 'Payment authorised.'}
  8.6    PASS     Every decline/error/timeout test card renders a distinct, non-spinner UI state
           8.6 every decline/error/timeout test card renders a distinct, non-spinner UI state
  8.7    PASS     Static denylist scan finds zero payment-provider identifiers
           148 files scanned across ('src', 'tests', 'scripts', 'pyproject.toml',
           'web/package.json', 'web/package-lock.json'), 0 hits
  8.8    PASS     No card number is present in any log, trace, DB row, or audit entry
           scanned 5 surfaces (response, DB row, audit hash, stdout, stderr) for all 5 documented
           test-card numbers -- none present
  8.9    PASS     PENDING older than TTL transitions to EXPIRED and releases the listing
           PENDING -> expired after the 15-minute TTL; listing hold released
  8.10   PASS     MOCK -- NO REAL PAYMENT banner is present and above the fold
           8.10 MOCK -- NO REAL PAYMENT banner is present and above the fold
  8.11   PASS     Client-computed monthly payment matches server recomputation to the cent
           8.11 client-computed monthly payment matches server recomputation to the cent
  8.12   PASS     Audit trail has one entry per transition with actor, timestamps, and gesture
                  provenance
           2 audit entries: submit(actor=user, draft->pending, note='checkout confirmed by a
           trusted click'), authorise(actor=system, pending->confirmed,
           event_id='auth_1a473a7b84d7441797db')
------------------------------------------------------------------------------
  12 passed, 0 failed, 0 pending
  GATE 8 GREEN
==============================================================================
```

Also re-run against live Postgres (`docker compose up -d postgres`, migration `0002_bookings_commerce`
applied) for the pure-Python criteria and the full test suite; 8.3/8.6/8.10/8.11's own spawned
backend is exercised against whatever `CARDINAL_DATABASE_URL` the invoking shell has set, same as
gate 7's — the run pasted above is the documented, unset-environment invocation (CONSTITUTION
III.7). See DECISIONS.md for a known gap this surfaced: a raw `uvicorn` subprocess on native
Windows cannot open an async Postgres connection at all (`ProactorEventLoop`, the same
psycopg/Windows interaction `src/adapters/db/session.py`'s `run_async` works around for CLI entry
points) — harmless for `docker compose up` (the container is Linux) and for every gate through P7
(none of their spawned-subprocess flows touched Postgres), but it means `scripts/gate_phase8.py`'s
own browser criteria run against the in-memory `BookingStore` whenever invoked directly on Windows
outside Docker, `CARDINAL_DATABASE_URL` set or not. `PostgresBookingStore` itself is real and
covered by `tests/integration/test_adapters_booking_store_postgres.py`, which runs through
pytest-asyncio's own `SelectorEventLoop` hook and is unaffected.

**8.7's evidence line updated 2026-08-08 when Phase 10 landed.** The term list and scan loop
now live in `scripts/gate_common.py`, shared with gate 10.3 rather than an independently
authored copy (DECISIONS.md D-044) — same scan scope, but the file-exclusion set grew by two
(the new `gate_common.py`/`gate_phase10.py`, both of which now also spell out a denylist
literally), and the repo has more files in it than it did when Phase 8 landed. Re-run for real
rather than hand-edited, per CONSTITUTION III.1.

### What shipped

| Area | Files |
|---|---|
| Booking state machine | `src/domain/booking.py` — `BookingState` (7 values, D-035), `BookingEvent`, `TRANSITIONS`, `apply_transition`, `BookingAuditEntry`/`new_audit_entry`, `Booking.with_transition`, `stale_pending` (pure, `now` passed in) |
| Financing calculator | `src/domain/financing.py` — `FinancingTerms`, `compute_monthly_payment` (standard amortisation, `Decimal`, zero-APR special case) |
| Payment contracts | `src/domain/payments.py` — `PaymentOutcome`, `OUTCOME_MESSAGES`, `PaymentIntent` (last4 + outcome hint only, D-036), `AuthResult`/`CaptureResult`/`VoidResult` |
| Mock gateway | `src/adapters/payments/{protocol,mock}.py` — `PaymentGateway` protocol, `MockPaymentGateway`, `MOCK_GATEWAY_BASE_URL` (a `mock://` compile-time constant), `CARD_OUTCOMES`/`outcome_for_card_number` (test/doc mirror of the client-side table) |
| Booking store | `src/adapters/booking_store.py` (protocol, `InMemoryBookingStore`, `PENDING_TTL_MINUTES`, `session_ref_to_uuid`, `expire_stale_bookings`), `src/adapters/db/booking_store.py` (`PostgresBookingStore`) |
| Schema | `migrations/versions/0002_bookings_commerce.py` — `bookings` gains `canonical`/`created_at`/`updated_at`, loses `ts`/`audit` (superseded by `canonical`, D-006's dual-storage shape); `src/adapters/db/models.py`'s `BookingRow` updated to match |
| Gesture tokens | `src/mcp/booking/gesture.py` — `GestureTokenStore`, 30s TTL, single-use (CONSTITUTION I.2 layer 3) |
| Checkout resource + App | `src/mcp/booking/resources.py` (`CHECKOUT_URI`, both resources now served off one registry), `src/mcp/booking/static/checkout.html` (MOCK banner, financing sliders, mock tokeniser, gesture-gated confirm flow) |
| Tool handlers | `src/mcp/booking/tools.py` — real `open_checkout`, new `mint_gesture_token`, real `confirm_booking`; module-level shared defaults (D-038); `src/mcp/booking/server.py` threads `store`/`booking_store`/`payment_gateway` through |
| Booking form draft carries its listing ref | `src/mcp/booking/static/booking_form.html` — echoes `source`/`source_id`/`offer_type` from its own `toolInput` into the submitted draft, so `open_checkout`/`confirm_booking` can price it |
| API wiring | `src/api/main.py` — `app.state.booking_store` (Postgres-or-memory, matching `build_store`'s own split), `CHECKOUT_URI` added to `RESOURCE_ROUTES` |
| Gate | `scripts/gate_phase8.py` — 8 pure-Python criteria + 4 Playwright-driven, same split gate 7 used for its own browser subset |
| Frontend tests | `web/tests/commerce.spec.ts`, `web/playwright.mcp-commerce.config.ts` — reuses `mcp-host-harness.html` unmodified (already resource-agnostic per P7) |
| Tests | `tests/unit/test_domain_{booking,financing}.py`, `tests/unit/test_adapters_payments.py`, `tests/unit/test_adapters_booking_store.py`, `tests/integration/test_adapters_booking_store_postgres.py`, `tests/unit/test_mcp_booking.py` (rewritten from P7's stub-pinning tests, the same treatment P6 gave P2's `ui-mcp` stubs) |

`confirm_booking` stayed exactly where P2 declared it — `audience=("app",)`, never registered on
a model-facing build (gate 8.2) — and P8 adds two more independent layers on top: a gesture token
`mint_gesture_token` mints only in response to a click the App has already checked `isTrusted` on,
single-use and 30-seconds-lived (gate 8.4), and every mutating call is keyed so a retried request
replays rather than double-books or double-charges (gate 8.5, backed by a real `UNIQUE
(session_id, idempotency_key)` constraint in Postgres, not just an in-memory check). Neither the
mock gateway nor the checkout App ever see a full card number reach the server — `_price_draft`
recomputes the authoritative total server-side from the same `adapter.quote()` path `get_quote`
already uses, so nothing about checkout trusts a client-supplied price or a client-supplied
outcome without the click-and-token gate in front of it.

### Deferred, deliberately

- **`[SCALE]` A real gateway behind `PaymentGateway`, feature-flagged.** The protocol
  (`src/adapters/payments/protocol.py`) is the whole seam PHASE-8 §5 asks for; nothing in this
  repository implements it besides the mock, by design (CONSTITUTION I.1, gate 8.7).
- **`[SCALE]` Refund/cancellation flows, partial states.** `BookingEvent.CANCEL` and `.ABANDON`
  are real, gate-8.1-tested transitions in the domain state machine, but no MCP tool triggers
  either yet — PHASE-8 §2's own `[SCALE]` line.
- **A live rehearsal of the model actually calling `open_checkout` inside a real session.**
  `src/agent/orchestrator.py` wires `store=self._store` into the model-facing `booking-mcp` build
  now, type-checked and unit-tested, but — the same D-015 reasoning already applied to gates
  3/5/6/7's live paths — nobody has yet run it against the real `claude` CLI.
- **A native-Windows, non-Docker `uvicorn` process serving real Postgres traffic.** Noted above;
  affects local dev ergonomics only, not any gate criterion or the Docker-based deployment path.

---

## Phase 9 — Observability ✅

Run on 2026-08-08, no container needed — every criterion is pure/deterministic code against
`DEMO_MODE` (D-015's reasoning, the same one gates 3/5/8 already established: nothing here
needs a live `ClaudeSDKClient` session or an `ANTHROPIC_API_KEY` to mean something).

```
==============================================================================
GATE 9 -- OBSERVABILITY -- OTel, Langfuse, eval harness, cost governance
==============================================================================
  9.1    PASS     A full session produces one trace containing spans for all four phases
           12 spans captured, all four phase spans present, all sharing
           trace_id=1ad252f2d1aa0dcafaf897aebd29cb75 with the session's own root span
  9.2    PASS     Every MCP tool call appears as a span with args hash and duration
           4 tool call span(s) across 4 distinct tools: ['tool.interview_turn',
           'tool.open_booking_form', 'tool.search_cars', 'tool.submit_booking_draft']
  9.3    PASS     Both researcher subagents appear as sibling spans with overlapping time ranges
           2 researcher spans, both children of phase.research,
           researcher.mock_autobazaar=[1786166728959755700,1786166728980216500] overlaps
           researcher.mock_drivenow=[1786166728959791500,1786166728980364100]
  9.4    PASS     Eval harness runs 30 personas headless and emits a scored report
           30 personas run (20 from P5's golden set, 10 end-to-end extras), 9 metrics scored:
           profile_completeness=1.000, precision_at_3=1.000, groundedness=1.000,
           constraint_compliance=0.000, guardrail_violations=0.000, escape_hatch_ratio=0.000,
           tool_call_rate=4.800, cost_per_session_usd=0.000, latency_p50_p95_s=0.186
  9.5    PASS     All thresholds in PHASE-9 §4 met; guardrail violations exactly 0
           9/9 metrics within threshold: profile_completeness 1.000 >= 0.95, precision_at_3
           1.000 >= 0.8, groundedness 1.000 == 1.0, constraint_compliance 0.000 == 0,
           guardrail_violations 0.000 == 0, escape_hatch_ratio 0.000 <= 0.15, tool_call_rate
           4.800 in 2-8, cost_per_session_usd 0.000 <= 0.4, latency_p50_p95_s 0.186 within
           p50<=8s/p95<=25s
  9.6    PASS     No PII in any exported span -- redaction hook asserted on a real export
           12 spans scanned, zero raw email/phone matches, 2 redaction marker(s) found
           (e.g. on tool.input.utterance)
  9.7    PASS     Cost per session <= $0.40 across the golden set, reported per role
           max $0.00/session across 30 personas; per role: {orchestrator: 0.0, extraction: 0.0,
           critic: 0.0, explainer: 0.0} -- DEMO_MODE makes zero live model calls (CONSTITUTION
           III.7), so this is a real $0.00, not an estimate
  9.8    PENDING  [SCALE] Prompt-cache hit rate > 0 across repeated sessions
           needs a live multi-turn ClaudeSDKClient session to produce a real
           cache_read_input_tokens signal -- DEMO_MODE makes zero model calls by construction
  9.9    PENDING  [SCALE] Eval regression > 5% fails CI
           CI-gated eval regression detection on every prompts/ or src/agent/ PR not built --
           [SCALE]; src/agent/evals.py's EvalReport is the mechanism a future CI job would diff
------------------------------------------------------------------------------
  7 passed, 0 failed, 2 pending
  GATE 9 GREEN (with 2 pending)
==============================================================================
```

Built directly against Phase 9, ahead of PLAN-00 §4's suggested under-deadline order (`... → 8
→ 11 → 9 → backfill 4/10`) — see DECISIONS.md D-039 for why that's not a CONSTITUTION III.2
violation and what was checked before starting. Phase 8 (Commerce) had already landed by the
time this work started.

### What shipped

| Area | Files |
|---|---|
| Tracing core | `src/agent/tracing.py` — `configure_tracing` (idempotent `TracerProvider` + resource, always-on in-memory exporter, optional Langfuse OTLP exporter when `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set), `RedactingSpanExporter`/`redact_attributes` (CONSTITUTION IV.1, export-path redaction ahead of any network call), `phase_span`/`tool_call_span`/`subagent_span`/`scoring_span` |
| MCP tool-call spans | `src/mcp/audience.py`'s `for_audience` wraps every registered tool's handler in a `tool.<name>` span using the raw `opentelemetry` API directly (no `mcp` → `agent` import, preserving PLAN-00 §2's one-way layering) — covers every live-path tool call on every server without touching 14 individual tool files |
| Phase/subagent spans | `src/agent/demo.py` — one `session` root span per run, one `phase.*` span per phase *stay* (RESEARCH revisited after a backward transition gets two), a `scoring.rank` span around `rank()` with weights + a determinism hash; `src/agent/research.py`'s `_research_one_source` opens a `researcher.<source>` span while `phase.research` is the ambient current span, so `asyncio.gather`'s tasks snapshot it as their parent and come out as genuine overlapping siblings (gate 9.3) |
| `decline_at_checkout` | `src/agent/demo.py`'s `run_demo_session` gained this optional flag — settles TRANSACT on `booking_status="abandoned"` instead of `submit_booking_draft`, the "decline at checkout" end-to-end path PHASE-9 §4's eval golden set calls for, which nothing had driven a session into before |
| Live-path instrumentation | `src/api/main.py`'s `lifespan` calls `configure_tracing()` + `ClaudeAgentSDKInstrumentor().instrument()` once, fire-and-forget (try/except, matches PHASE-9 §8's risk table) — real and wired, gate-unexercised the same way D-015 leaves the rest of live orchestration unexercised |
| Eval harness | `src/agent/evals.py` — `run_eval_harness` scores PHASE-9 §4's nine metrics per persona and in aggregate: profile completeness, precision@3 (D-024-style structural self-consistency), groundedness (no `[unverified]` marker), constraint compliance (an independent re-check of the final top-3 against every hard filter/budget/date, not a re-read of `critic_pass`'s own verdict), guardrail violations, escape-hatch ratio (a real `compile_results_surface` call per persona with survivors, genuinely 0 `compose_surface` calls since `DEMO_MODE` has no model to reach for it with), tool-call rate, cost/session, latency p50/p95 |
| 30-persona golden set | `tests/fixtures/demo/eval_extra_personas.json` — 10 new personas (3 backward-transition, 3 zero-result/infeasible, 2 decline-at-checkout, 2 general coverage) alongside P5's existing 20 (`golden_set.json`) |
| Gate | `scripts/gate_phase9.py` |
| Tests | `tests/unit/test_agent_tracing.py` (14), `tests/unit/test_agent_evals.py` (10) |

Two of the nine eval metrics needed an explicit, documented substitution rather than a
fabricated number — both because `DEMO_MODE` is genuinely a scripted, non-agentic replay
(CONSTITUTION III.7), not a live multi-turn session:

- **Tool-call rate** counts every audited tool call per session (interview turns, searches,
  booking calls), not `search_cars` alone — `DEMO_MODE`'s RESEARCH phase issues exactly one
  `search_cars` audit entry per turn-in-phase regardless of how many of the two marketplaces
  it fans out to underneath (D-013's "the agent never learns marketplaces are plural" holds
  inside `DEMO_MODE` too), so counting search calls alone would floor near 1 for most personas.
- **Cost per session** reports a real $0.00 — `DEMO_MODE` makes zero model calls by
  construction, so that is the honest number, not an estimate against per-token rates for
  calls that never happened. Live per-role cost governance (PHASE-9 §5, mostly `[SCALE]`)
  waits on the live rehearsal PROGRESS.md's "Next" list already tracks.

`src/agent/evals.py`'s own `infeasible_mismatches` field (not one of the nine gated metrics)
caught a real, useful fact while this was being built: one of P5's original 20 golden
personas ("Golden 18 — Wagon Buyer Tight Budget") is genuinely infeasible against the seeded
catalogue, matching gate 5.4's own "19/20 feasible" finding — surfaced as a diagnostic rather
than hard-coded as a named exception, since that fact depends on the catalogue seed/generator
and would go stale silently otherwise (the same reasoning D-002 already established for gate
1.8's cohort statistics).

### Deferred, deliberately

- **`[SCALE]` Prompt-cache hit rate tracking** (PHASE-9 §5) — gate 9.8. `cache_read_input_tokens`
  only exists on a real, repeated `ClaudeSDKClient` session; `DEMO_MODE` makes zero model calls.
- **`[SCALE]` CI-gated eval regression detection** (PHASE-9 §4) — gate 9.9. `EvalReport` is the
  artifact a future CI job would diff two runs of; the diffing and the CI wiring aren't built.
- **`[SCALE]` Per-session cost budget + hard cap, cheap-model routing under pressure,
  compaction** (PHASE-9 §5's levers 2-5) — no live session exists yet to threaten a real budget.
- **`[SCALE]` Reasoning-replay timeline surfaced in-product** (PHASE-9 §6) — the data it would
  read (P4's decision journal joined to the trace) already exists; no UI reads it yet.
- **`[SCALE]` Online evals on real sessions, sampled** — needs live traffic to sample from.
- **A live rehearsal of `ClaudeAgentSDKInstrumentor`'s auto-generated spans.** `src/api/main.py`
  wires it in real and fire-and-forget, but — the same D-015 reasoning already applied to every
  other phase's live path — nobody has yet run it against the real `claude` CLI.

---

## Phase 10 — Trust ✅

Run on 2026-08-08, no container needed — every criterion is pure/deterministic code against
`DEMO_MODE`'s real pipeline or a static file scan (D-015's reasoning, already applied to gates
3/5/8/9).

```
==============================================================================
GATE 10 -- TRUST -- Injection defence, PII, tenancy, threat model
==============================================================================
  10.1   PASS     Injection corpus (~30 attempts): zero succeed
           30 attempts across 6 categories (delimiter_escape=5, encoded_payloads=5,
           instruction_override=5, memory_poisoning=5, role_confusion=5,
           tool_call_injection=5), zero succeeded: identical score, identical rationale,
           single real wrapper tag, every time
  10.2   PASS     Memory-poisoning attempt does not write to episodic memory
           0 memory-write-shaped tools across 6 server x audience builds; 5
           memory-poisoning listings seeded into a real catalogue, session reached
           booking_status='draft_submitted', zero leakage into the profile or the
           decision journal
  10.3   PASS     Denylist scan: zero hits across source, deps, lockfiles
           148 files scanned across ('src', 'tests', 'scripts', 'pyproject.toml',
           'web/package.json', 'web/package-lock.json') for 10 payment-provider (I.1) +
           7 BMW Group endpoint (I.3) terms, 0 hits
  10.4   PASS     Listing text reaches the model wrapped and labelled trust="untrusted"
           get_listing(mock_drivenow:DN-1001).description arrives as '<listing_content
           listing_id="DN-1001" source="mock_drivenow" trust="un'... (full text wrapped,
           labelled trust="untrusted")
  10.5   PENDING  [SCALE] PII scan over logs and a real span export: zero findings
           the span-export half is already built and gated -- gate 9.6 asserts zero raw
           PII in a real OTel export via RedactingSpanExporter (CONSTITUTION IV.1); a
           log-line scan and memory-tier redaction are not built
  10.6   PENDING  [SCALE] Two-tenant isolation test: zero cross-visibility in all stores
           multi-tenancy not built -- no tenant_id column anywhere in the schema
  10.7   PENDING  [SCALE] pip-audit + npm audit: no high/critical
           neither scanner wired into make verify or CI yet
  10.8   PENDING  [SCALE] Every 3D asset has an attribution entry
           docs/ATTRIBUTION.md does not exist; the eight PowertrainExplainer GLBs are
           hand-built placeholders (D-028), not licensed geometry -- nothing to
           attribute yet
  10.9   PENDING  [SCALE] docs/THREAT-MODEL.md exists with no open criticals
           not written yet; PHASE-10 §8's five-adversary table lives only in the plan doc
------------------------------------------------------------------------------
  4 passed, 0 failed, 5 pending
  GATE 10 GREEN (with 5 pending)
==============================================================================
```

### What shipped

| Area | Files |
|---|---|
| Injection defence (pure) | `src/domain/trust.py` — `detect_injection` (cheap best-effort classifier over ~20 phrasing patterns spanning instruction-override/role-confusion/memory-poisoning), `escape_untrusted_text`/`_escape_attr` (unconditional `<`/`>`/`&` escaping), `wrap_listing_content` (the concrete `<listing_content listing_id=... source=... trust="untrusted">` form CONSTITUTION I.4 names) |
| `get_listing` wired to wrap | `src/mcp/marketplace/tools.py` — the only tool that ever returns a listing's full `description` now returns `wrap_listing_content(listing)` in that field instead of the raw string; `search_cars`/`compare_listings` never carried it in the first place (`ListingSummary`'s own docstring) |
| Standing untrusted-content rule | `prompts/orchestrator_system.md`, `researcher.md`, `critic.md`, `explainer.md` — every prompt that can reach `get_listing` (directly or as a subagent) states the rule once, since Claude Agent SDK subagents run on their own `AgentDefinition.prompt`, not inheriting the orchestrator's `system_prompt` |
| Denylist scan (shared) | `scripts/gate_common.py` — `PAYMENT_PROVIDER_TERMS`, `DENYLIST_SCAN_DIRS`, `DENYLIST_EXTRA_FILES`, `DENYLIST_AUTHORING_FILES`, `scan_for_terms()`, factored out of gate 8.7 and reused by gate 10.3 (DECISIONS.md D-044) |
| `resolved_tools` zero-tool fix | `src/mcp/audience.py` — handles a server with no registered tools for an audience (e.g. `ui-mcp`'s "app" build) without raising (DECISIONS.md D-045) |
| Injection corpus | `tests/fixtures/security/injection_corpus.json` — 30 entries, 5 each across `instruction_override`, `role_confusion`, `delimiter_escape`, `encoded_payloads`, `tool_call_injection`, `memory_poisoning` |
| Gate | `scripts/gate_phase10.py` |
| Tests | `tests/unit/test_domain_trust.py` (11), `tests/unit/test_agent_injection_corpus.py` (corpus-parametrised: score purity, rationale/grounding purity, wrapper-tag integrity, classifier recall on the three plainly-worded categories, tool-shape + end-to-end memory-poisoning checks), `tests/unit/test_mcp_marketplace.py` (+1, `get_listing`'s wrapped output) |

Gate 10.1's evidentiary bar is structural, matching D-015's reasoning one phase further: with
no live model in the loop, "zero succeed" is proven as identical `ScoreBreakdown`, identical
rationale text, and exactly one real `<listing_content>` tag pair surviving escaping, for every
one of the 30 entries against the same base listing with only its `description` swapped —
never as "the classifier caught it" or "a model declined to obey it" (DECISIONS.md D-046).
Writing the corpus this way is also what caught a real bug before it shipped: the first version
of `wrap_listing_content`'s flagged-note interpolated the raw, matched fragment of untrusted
text via `{flag.matched!r}` without escaping it first, so a payload built to exploit exactly
that (`DE-01`, containing a literal `</listing_content>`) produced three `<` and two `>` in the
wrapped output instead of two of each — CONSTITUTION III.8's "watch it fail, then make it pass"
working exactly as intended (DECISIONS.md D-042).

The BMW Group denylist (`BMW_GROUP_ENDPOINT_TERMS` in `scripts/gate_phase10.py`) is
deliberately endpoint-shaped (`bmwgroup.com`, `connecteddrive`, `mini.co.uk`, …), never the
bare word "BMW" — that word appears throughout `src/adapters/catalogue/taxonomy.py`'s
legitimate seeded brand pool, exactly the case CONSTITUTION I.3 carves out ("brand names in
our own generated dataset are fine").

### Deferred, deliberately

- **`[SCALE]` PII redaction across logs and the memory tier** (PHASE-10 §4) — gate 10.5. The
  span-export half already shipped in P9 (gate 9.6); a log-line regex+entropy scan and
  memory-tier redaction wait on a log sink and on P4's episodic memory, neither of which exist.
- **`[SCALE]` Multi-tenant isolation** (PHASE-10 §5) — gate 10.6. No `tenant_id` anywhere in
  the schema; this is a single-tenant system by construction today, not by an unenforced
  convention. PHASE-10 §10's own risk table flags this as expensive to add late — still true,
  still deferred, per CONSTITUTION III.3.
- **`[SCALE]` Rate limiting and abuse controls, secrets rotation** (PHASE-10 §2) — not built;
  no gate criterion names either directly.
- **`[SCALE]` Supply-chain: `pip-audit`/`npm audit` in CI, licence audit, pinned-hash
  verification** (PHASE-10 §7) — gate 10.7.
- **`[SCALE]` `docs/ATTRIBUTION.md`** (PHASE-10 §7) — gate 10.8. Nothing to attribute yet;
  P6's GLBs are hand-built placeholders (D-028), not licensed third-party assets.
- **`[SCALE]` `docs/THREAT-MODEL.md`** (PHASE-10 §8) — gate 10.9. The five-adversary table
  exists in `plans/PHASE-10-TRUST.md` §8 itself; not yet promoted to a standalone, gated file.
- **A live rehearsal of a real model actually reading a `<listing_content trust="untrusted">`
  block and declining to follow it.** Every mechanism here is architecturally enforced
  (structured-field scoring, escaping, tool invisibility) rather than reliant on the model
  choosing correctly, which is the point — but nobody has yet watched a real session try one
  of these 30 entries end to end, the same D-015 gap every other phase's live path still has.

---

## Phase 11 — Delivery ✅

Run on 2026-08-08. 11.1/11.2/11.5/11.6 against a real `docker compose build && up`, rebuilding
the `cardinal` project in place (the same containers a prior session had left running 15h
earlier — no `-v`, the named Postgres volume was reused, not destroyed). 11.3/11.4 against a
disposable backend on its own port with the environment scrubbed to just `DEMO_MODE=true`,
driving the real product (`index.html`, not a harness page) through a real Chromium instance.
11.7/11.9/11.10 are pure filesystem/subprocess checks.

> **Run this one on a clean machine state.** Found while verifying P14 (2026-08-09): 11.10
> re-runs gates 0–11, and a Vite preview server left listening on `:4173` by an *earlier*
> gate's Playwright run gets reused (`reuseExistingServer: !CI`) with whatever
> `CARDINAL_API_PORT` it was started with. Gate 7 then talks to the wrong backend — with a
> `docker compose` stack on `:8000` it silently answers, so the run produces an empty report
> and all ten of gate 7's criteria fail as "no test titled '7.N ...' found". Gate 7 standalone
> was green in the same session, before and after, and gate 11 re-ran fully green
> (8 PASS / 3 PENDING, 11.10 included) once the stray process was killed. Check `:4173` is
> free before running gate 11; it is the same family of mistake D-033 already records for
> `:8000`.

```
==============================================================================
GATE 11 -- DELIVERY -- Docker, deploy, CI/CD, docs, demo assets
==============================================================================
  11.1   PASS     Clean clone -> docker compose up -> all services healthy within 120s
           all 4 services healthy within 120s: {'api': 'healthy', 'booking': 'healthy',
           'postgres': 'healthy', 'web': 'healthy'}
  11.2   PASS     Seed runs automatically; /health reports >=100 listings
           /health -> {'status': 'ok', 'backend': 'postgres', 'demo_mode': False, 'listings':
           240, 'sources': {'mock_autobazaar': 130, 'mock_drivenow': 110}}
  11.3   PASS     Playwright e2e walks all seven beats and screenshots each
           web/tests/demo-e2e.spec.ts walked all seven beats and screenshotted each --
           stats={'expected': 1, 'skipped': 0, 'unexpected': 0, 'flaky': 0}
  11.4   PASS     e2e passes with the entire environment unset except DEMO_MODE=true
           backend launched with {CARDINAL_DATABASE_URL, CARDINAL_BOOKING_MCP_URL,
           ANTHROPIC_API_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST} removed
           and only DEMO_MODE=true set -- stats={'expected': 1, 'unexpected': 0}
  11.5   PASS     'booking' service resolves on a distinct hostname from 'web'
           'booking' (src.mcp.booking.http, no published port) and 'web' (builds
           ./web/Dockerfile) are distinct compose services, each its own hostname on the
           compose network
  11.6   PASS     Every image runs as non-root; no image exceeds 800 MB
           api: user='cardinal' size=177MB; booking: user='cardinal' size=177MB; web:
           user='101' size=21MB
  11.7   PASS     .env.example covers every variable read anywhere in the codebase (scan
                  asserts)
           10 variable(s) read in src/ + web/src/ + vite.config.ts, all in .env.example:
           ['ANTHROPIC_API_KEY', 'BOOKING_MCP_HTTP_HOST', 'BOOKING_MCP_HTTP_PORT',
           'CARDINAL_API_PORT', 'CARDINAL_BOOKING_MCP_URL', 'CARDINAL_DATABASE_URL',
           'DEMO_MODE', 'LANGFUSE_HOST', 'LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY']
  11.8   PENDING  README's run instructions executed verbatim on a clean machine
           by definition a human, on a machine that has never seen this repo, following
           README.md's 'Run it' section verbatim -- nothing this script runs can stand in for
           that. See README.md's Run it section.
  11.9   PENDING  Deck and video present under docs/
           deck present (cardinal-deck.pptx); video not recorded -- see
           docs/VIDEO-SCRIPT.md for the shot list, recorded against DEMO_MODE per
           web/tests/demo-e2e.spec.ts's own seven beats
  11.10  PASS     make verify green: every gate 0-11
           gates 0..10 each exit 0 (11 gates checked; gate 11 is this run itself)
  11.11  PENDING  [SCALE] Public deployment reachable and healthy
           no public deployment exists -- PHASE-11 SS2 marks this [SCALE]
------------------------------------------------------------------------------
  8 passed, 0 failed, 3 pending
  GATE 11 GREEN (with 3 pending)
==============================================================================
```

### What shipped

| Area | Files |
|---|---|
| Multi-stage, non-root, healthchecked Dockerfiles | `Dockerfile` (shared by `api`/`booking`: venv-builder stage + slim runtime, `USER cardinal`) — `web/Dockerfile` (Node builder → `nginxinc/nginx-unprivileged:alpine` runtime) |
| Four-service compose | `docker-compose.yml` — `postgres`, `booking` (own service, no published port, CONSTITUTION II.5), `api` (`CARDINAL_BOOKING_MCP_URL` pointed at `booking`), `web` (nginx reverse-proxying `/health`, `/sessions`, `/adapters`, `/mcp-apps`, `/demo` to `api`) |
| Config surface | `.env.example` — every variable any of `src/`, `web/src/`, `web/vite.config.ts` actually reads, none defaulted to a secret |
| `DEMO_MODE` reaches the real web app for the first time | `src/agent/demo_stream.py` (new) — `run_streamed_demo` drives the real phase machine/extractor/research dispatcher/P5 ranking through the *actual* `render_progress`/`render_tco`/`render_results`/`render_detail`/`open_booking_form` tool handlers (`for_audience(...).handler`, the same choke point a live tool call goes through), so DEMO_MODE finally pushes real A2UI/MCP-App messages over the real SSE transport instead of only mutating `SessionState` in memory (D-049) |
| Reactive checkout hand-off | `src/api/main.py`'s `mcp_app_rpc` calls `demo_stream.on_draft_submitted` (backgrounded, D-051) after a real `submit_booking_draft` RPC succeeds — checkout opens because a human's real click submitted the form, not because the script pre-decided it would |
| Score-breakdown click-through | `src/agent/demo_stream.py`'s `handle_explain_action`, wired from `session_actions`; `web/src/a2ui/catalog.tsx`'s `CarCard` now dispatches a real `explain` action on click (previously static markup with no handler at all) |
| `booking-mcp` as a real standalone service | `src/mcp/booking/http.py` — `BOOKING_MCP_HTTP_HOST`/`_PORT` env overrides so it can bind `0.0.0.0` in its own container; `src/api/main.py`'s `_ensure_booking_mcp_http` becomes a no-op when `CARDINAL_BOOKING_MCP_URL` is set |
| `Start Demo` control | `web/src/App.tsx` — fetches `/health`'s `demo_mode` flag, shows a button that `POST`s `/demo/{session}/start`; everything downstream (SSE canvas, MCP App host) was already wired by P6/P7 |
| Seven-beat e2e | `web/tests/demo-e2e.spec.ts` + `web/playwright.demo.config.ts` — walks the real product end to end, screenshotting each beat to `docs/screenshots/` (11 images) |
| Real gate | `scripts/gate_phase11.py` — replaces the PENDING stub; 11.1/11.2/11.5/11.6 against real Docker, 11.3/11.4 against a scrubbed-env disposable backend, 11.7 a same-file constant-resolving env-var scan, 11.10 a gate-0..10 sweep |
| Licence | `LICENSE` (MIT), DECISIONS.md D-047 recording the (confirmed clean-room) basis for not inheriting the user's other AGPL-3.0 repo's terms |
| Docs | `README.md` rewritten to PHASE-11 §5's order (paragraph, hero screenshot, run instructions, architecture, what's-real-vs-mocked table, requirement traceability table, licence); `docs/cardinal-deck.pptx` (10 slides); `docs/VIDEO-SCRIPT.md` (shot list, not yet recorded) |

Building the streamed demo driver exercised code paths gates 3/5 had only ever checked the
*shape* of, not the *content* of, and surfaced two real, pre-existing bugs neither gate's own
criteria happened to catch (DECISIONS.md D-050):

- `src/agent/extraction.py`'s `DemoSlotExtractor` read "we're planning to buy, not rent" as
  **RENT** — first-pattern-wins matching found "rent" appearing in the sentence at all, before
  ever checking for "buy". This has been silently true since Phase 3 landed (gate 3.1 only
  asserts a profile becomes *complete*, never that a slot holds the *correct* value); Family
  Fatima, one of gate 3.1's own ten personas, has been quietly researched as a renter the whole
  time. Fixed with a negation-stripping pass ahead of matching, plus a reordered
  explicitly-undecided pattern that could never have matched in its original position. New
  parametrised regression test, 11 cases:
  `tests/unit/test_agent_extraction.py::test_goal_extraction_reads_the_stated_option_not_the_ruled_out_one`.
- The top-ranked survivor under a buy goal is not always buy-eligible — `src/domain/ranking.py`'s
  `_reference_price` (P5, working exactly as designed) falls back to `market_value` for a
  rent-only listing, so it can rank and display a price without ever supporting a purchase
  quote. `demo_stream.py`'s booking beat now selects the first *buy-eligible* survivor in rank
  order rather than assuming rank 1 always matches the stated goal.
- A genuine race: pushing checkout's `mcp_app_open` SSE message immediately after a
  `submit_booking_draft` RPC succeeded (but before that RPC's own HTTP response reached the
  browser) tore down the outer iframe the response was still in flight to, via React remounting
  `McpAppHost` on the new message — `net::ERR_ABORTED`, caught only by running the real
  Playwright spec in a real browser (every curl-based check of the same backend logic passed,
  since curl never has an iframe to tear down). Fixed by backgrounding the hand-off and pacing
  it behind a short, deliberate delay (D-051).

None of gates 3/5's own criteria needed to change — both bugs were real and pre-existing, not
introduced by this phase, and both now have a regression test that would have caught them
in Phase 3/5 had it existed then.

### Deferred, deliberately

- **`[SCALE]` Public deployment** (PHASE-11 §2) — gate 11.11. No hosted instance exists; every
  criterion above is proven against a local Docker stack.
- **`[SCALE]` CI/CD with image publishing** (PHASE-11 §2) — nothing runs `make verify`/gate 11
  automatically on a push; no registry receives a built image.
- **`[SCALE]` `docs/ARCHITECTURE.md`, an ADR index, a contributor guide** (PHASE-11 §2) — the
  architecture diagram lives in the README and `plans/PLAN-00-OVERVIEW.md` §3; `DECISIONS.md`
  itself is the ADR log, just not indexed as one.
- **The demo video itself** — gate 11.9 half-passes: the deck is real and checked in, the shot
  list (`docs/VIDEO-SCRIPT.md`) is written against the same seven beats the e2e spec proves
  render, but recording a screen capture with narration is a human action no script here can
  perform.
- **Gate 11.8's clean-machine walkthrough** — by construction a human, on a machine that has
  never seen this repo, following `README.md`'s Run It section verbatim. Everything the rest of
  gate 11 can mechanically stand in for, it does; this one criterion it cannot.

---

## Phase 0 — Foundation ✅

Not the assignment, but Phase 1 could not stand without it: the `Listing` contract, the layering it
depends on, and the gate harness that runs both. Built to the point where P1's gate was meaningful,
then closed out fully once P3 gave 0.7 something to assert against.

```
  0.1    PASS     every domain model round-trips its fixture JSON      17 passed
  0.2    PASS     Money rejects float; arithmetic preserves Decimal     8 passed
  0.3    PASS     import-boundary scan finds zero violations            7 passed
  0.4    PASS     mypy --strict src/domain reports zero errors          11 source files
  0.5    PASS     specs/ holds constitution, spec, plan and tasks, all non-empty
  0.6    PASS     every gate script exists and runs to completion
  0.7    PASS     [SCALE] prompts live in files; no long prompt strings in src/
  7 passed, 0 failed, 0 pending  ->  GATE 0 GREEN
```

**0.7 closed when Phase 3 landed.** `prompts/` didn't exist because no prompt did until P3; the
criterion was written first (CONSTITUTION III.8) and started asserting the moment the six
`prompts/*.md` files and P3's own 200-char scan (gate 3.7, the same rule) appeared.

**0.5 closed 2026-08-08.** `uvx --from git+https://github.com/github/spec-kit.git specify init
--here --integration claude --script sh` was run against current spec-kit `HEAD` (`684b3d8e`),
which scaffolds `.specify/` (live templates + memory) and `.claude/skills/speckit-*` rather than
the flat, dot-command layout PHASE-0 §7 was written against. `specs/constitution.md`, `spec.md`,
`plan.md`, and `tasks.md` were authored by hand against the installed templates —
`.specify/templates/{constitution,spec,plan,tasks}-template.md` — with real Cardinal content (the
domain contracts, the phase map, the twelve phases' actual exit-gate criteria), not placeholder
text. `.specify/memory/constitution.md` carries an identical copy, since that's the path the
`speckit-*` skills read/write at runtime if invoked later. See `DECISIONS.md` D-011 for why the
gate script's flat-path check was kept as-is rather than rewritten to match the tool's nested
default.

All twelve `[MVP]` domain models from PHASE-0 §4 exist and round-trip. `tests/test_layer_boundary.py`
now requires `domain`, `adapters`, `mcp` and `agent` all four — `agent` joined when P3 landed.

---

## Verification, as run

Two different runs, deliberately shown separately — they exercise different amounts of the stack:

```
# 2026-08-07, docker compose up (Postgres 16 + pgvector live)
ruff check src tests scripts          All checks passed!
ruff format --check                   57 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/adapters src/api             Success: no issues found in 19 source files
pytest tests -q                       133 passed, 3 skipped
gates 0..11                           all exit 0

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after closing gate 0.5
ruff check src tests scripts          All checks passed! (one pre-existing unsorted import in
                                       src/mcp/audience.py fixed in passing)
ruff format --check                   60 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/adapters src/api             Success: no issues found in 19 source files
pytest tests -q                       107 passed, 29 skipped
gates 0..11                           all exit 0 (0 GREEN w/ 1 pending, 1 GREEN, 2..11 PENDING-by-design)

# 2026-08-08, no container — after Phase 2 (MCP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   75 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/adapters src/api src/mcp     Success: no issues found in 33 source files
pytest tests -q                       133 passed, 29 skipped
gates 0..11                           all exit 0 (0 GREEN w/ 1 pending, 1 GREEN, 2 GREEN w/ 1 pending,
                                       3..11 PENDING-by-design)

# 2026-08-08, docker compose up -d postgres (Postgres 16 live) — after Phase 3 (Agent) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   92 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 44 source files
pytest tests -q                       232 passed, 3 skipped
gates 0..3 --require-stack            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN
gates 4..11                           all PENDING-by-design, exit 0

# 2026-08-08, docker compose up -d postgres (Postgres 16 live) — after Phase 4 (Memory, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   95 files already formatted
mypy --strict src/domain              Success: no issues found in 11 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 45 source files
pytest tests -q                       248 passed, 3 skipped
gates 0..4 --require-stack            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN,
                                       4 GREEN w/ 5 pending
gates 5..11                           all PENDING-by-design, exit 0

# 2026-08-08, docker compose up -d postgres (Postgres 16 live) — after Phase 5 (Reasoning, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   103 files already formatted
mypy --strict src/domain              Success: no issues found in 14 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 45 source files
pytest tests -q                       306 passed, 3 skipped
gates 0..5 --require-stack            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN,
                                       4 GREEN w/ 5 pending, 5 GREEN w/ 1 pending
gates 6..11                           all PENDING-by-design, exit 0

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after Phase 6 (Generative UI, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   116 files already formatted
mypy --strict src/domain              Success: no issues found in 14 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 52 source files
pytest tests -q                       310 passed, 37 skipped
gates 0..6                            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1 pending,
                                       4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6 GREEN w/ 1 pending
gates 7..11                           all PENDING-by-design, exit 0
web/: npx tsc -b --noEmit             clean, no errors
web/: npx playwright test             6 passed (golden-fixture render, zero console errors)

# 2026-08-08, docker compose up (Postgres 16 live) — after Phase 7 (MCP Apps) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   122 files already formatted
mypy --strict src/domain              Success: no issues found in 14 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 57 source files
pytest tests -q                       321 passed, 37 skipped
gates 0..7                            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1 pending,
                                       4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6 GREEN w/ 1
                                       pending, 7 GREEN
gates 8..11                           all PENDING-by-design, exit 0
web/: npx tsc -b --noEmit             clean, no errors
web/: npx playwright test (gate 6)    6 passed (render.spec.ts only -- testMatch keeps gate 7's
                                       mcp-apps.spec.ts out of this run and vice versa)
web/: npx playwright test (gate 7)    10 passed (web/tests/mcp-apps.spec.ts, one per criterion)

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after Phase 8 (Commerce) landed
ruff check src tests scripts          All checks passed! (one pre-existing unsorted import in
                                       src/agent/demo.py fixed in passing)
ruff format --check                   136 files already formatted
mypy --strict src/domain              Success: no issues found in 16 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 64 source files
pytest tests -q                       374 passed, 40 skipped
gates 0..8                            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1
                                       pending, 4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6
                                       GREEN w/ 1 pending, 7 GREEN, 8 GREEN
gates 9..11                           all PENDING-by-design, exit 0
web/: npx tsc -b --noEmit             clean, no errors
web/: npx playwright test (gate 6)    6 passed
web/: npx playwright test (gate 7)    10 passed
web/: npx playwright test (gate 8)    4 passed (web/tests/commerce.spec.ts, one per browser
                                       criterion)

Also re-run with `docker compose up -d postgres` live and `CARDINAL_DATABASE_URL` set, migration
`0002_bookings_commerce` applied: `pytest tests -q` → 411 passed, 3 skipped (the 3 remaining
skips are `mock_autobazaar`'s rental-only contract cases, unrelated to a container); gates 0..8
with `--require-stack` where applicable all GREEN, including
`tests/integration/test_adapters_booking_store_postgres.py` (3 tests, otherwise skipped).

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after Phase 9 (Observability) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   139 files already formatted
mypy --strict src/domain              Success: no issues found in 16 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 65 source files
pytest tests -q                       398 passed, 40 skipped
gates 0..9                            0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1
                                       pending, 4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6
                                       GREEN w/ 1 pending, 7 GREEN, 8 GREEN, 9 GREEN w/ 2 pending
gates 10..11                          all PENDING-by-design, exit 0

# 2026-08-08, no container (CARDINAL_DATABASE_URL unset) — after Phase 10 (Trust, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   142 files already formatted
mypy --strict src/domain              Success: no issues found in 17 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 65 source files
pytest tests -q                       519 passed, 40 skipped
gates 0..10                           0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1
                                       pending, 4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6
                                       GREEN w/ 1 pending, 7 GREEN, 8 GREEN, 9 GREEN w/ 2
                                       pending, 10 GREEN w/ 5 pending
gate 11                               PENDING-by-design, exit 0
web/: npx playwright test (gate 6)    6 passed
web/: npx playwright test (gate 7)    10 passed
web/: npx playwright test (gate 8)    4 passed
```

```
# 2026-08-08, docker compose up (real 4-service stack: postgres/api/booking/web) — after
# Phase 11 (Delivery, MVP) landed
ruff check src tests scripts          All checks passed!
ruff format --check                   143 files already formatted
mypy --strict src/domain              Success: no issues found in 17 source files
mypy src/agent src/adapters src/api src/mcp   Success: no issues found in 66 source files
pytest tests -q                       530 passed, 40 skipped
gates 0..11                           0 GREEN, 1 GREEN, 2 GREEN w/ 1 pending, 3 GREEN w/ 1
                                       pending, 4 GREEN w/ 6 pending, 5 GREEN w/ 1 pending, 6
                                       GREEN w/ 1 pending, 7 GREEN, 8 GREEN, 9 GREEN w/ 2
                                       pending, 10 GREEN w/ 5 pending, 11 GREEN w/ 3 pending
web/: npx tsc -b --noEmit             clean, no errors
web/: npx playwright test (gate 6)    6 passed
web/: npx playwright test (gate 7)    10 passed
web/: npx playwright test (gate 8)    4 passed
web/: npx playwright test (gate 11)   1 passed (web/tests/demo-e2e.spec.ts, all seven beats +
                                       the audit-log trace, screenshotted to docs/screenshots/)
```

The jump from 519 to 530 passed is Phase 11's new `tests/unit/test_agent_extraction.py`
regression coverage (11 parametrised cases) for D-050's goal-extraction negation bug — found
while building `src/agent/demo_stream.py`, not introduced by it. Nothing else regressed: every
test that existed before Phase 11 still passes unchanged; gate 8's 8.7 evidence changed from
148 to 149 files scanned purely because the repo now has one more file in the scanned tree
(`src/agent/demo_stream.py` itself), not from a denylist behaviour change.

The jump from 398 to 519 passed is Phase 10's new `tests/unit/test_domain_trust.py` (11:
`detect_injection`, `escape_untrusted_text`, `wrap_listing_content`, including the
delimiter-escape/note-leak case D-042 records) and `tests/unit/test_agent_injection_corpus.py`
(corpus-parametrised over all 30 entries three ways — score purity, rationale/grounding
purity, wrapper-tag integrity — plus classifier-recall checks on the three plainly-worded
categories and two tool-shape/end-to-end memory-poisoning tests), plus one new test in
`tests/unit/test_mcp_marketplace.py` for `get_listing`'s wrapped output. Nothing regressed:
every test that existed before Phase 10 still passes unchanged. Gate 8's 8.7 evidence changed
(148 files scanned, was 142) purely from sharing its scan mechanism with gate 10.3
(DECISIONS.md D-044), not from a behaviour change; gates 2.2/2.5 (tool count, `get_listing`
token size) still pass but their printed numbers shift slightly (15 tools unchanged from P8,
`get_listing` now 354 tokens vs. 327 — still well inside gate 2.5's 800-token cap) because
`get_listing`'s `description` field is now the wrapped string, not the raw one.

The jump from 374 to 398 passed is Phase 9's new `tests/unit/test_agent_tracing.py` (14 tests:
redaction, span shape, phase/session trace-id nesting, subagent-span parenting and overlap,
PII-before-a-captured-span redaction) and `tests/unit/test_agent_evals.py` (10 tests:
`_violates_constraints`/`_satisfies_profile` unit cases plus three eval-harness integration
tests against the 10-persona extra fixture). Nothing regressed: every test that existed before
Phase 9 still passes unchanged; gate 1's docker-compose container being already up from earlier
in the session is why it reports a hard `PASS` rather than `PENDING` in this run without
`CARDINAL_DATABASE_URL` explicitly set — the same `--require-stack`-independent probe 1.10 has
always used when something is actually listening on the expected port.

Gate 1 shows `backend=postgres` this run (the container was already up from earlier the same
session, not started fresh for this pass) — the same code path 1.10's `--require-stack` run
exercises. Gate 3's 3.2 and gate 4's 4.1 report `PENDING` rather than `PASS` in the `gates 0..7`
line above because that pass ran without `--require-stack`; both are unchanged since their own
phases landed and are not re-verified here.

The jump from 321 to 374 passed is Phase 8's new `tests/unit/test_domain_{booking,financing}.py`,
`tests/unit/test_adapters_{payments,booking_store}.py` (36 tests), plus `tests/unit/
test_mcp_booking.py`'s rewrite from P7's four-tool-stub-pinning shape to nineteen tests covering
the real `open_checkout`/`mint_gesture_token`/`confirm_booking` behaviour (the same treatment P6
gave P2's `ui-mcp` stub tests). `tests/integration/test_adapters_booking_store_postgres.py` (3
tests) only runs with a container, accounting for part of the no-container/live-container skip
gap. Nothing regressed: every test that existed before Phase 8 still passes unchanged, and gate
2.2's tool count moved from 14 to 15 (booking-mcp's new `mint_gesture_token`) — the only P2 gate
arithmetic P8 had to touch, not a P2 regression.

The jump from 310 to 321 passed is Phase 7's new `tests/unit/test_mcp_apps.py` (8 tests) plus
three new tests added to `tests/unit/test_mcp_booking.py` (`test_open_booking_form_pushes_a_
mount_app_message_through_the_sink`, `test_submit_booking_draft_is_idempotent_per_draft_id`,
`test_booking_form_resource_is_registered_with_declared_csp`) — 11 new, net of zero removed.
Nothing regressed: every test that existed before Phase 7 still passes unchanged.

The jump from 248 to 306 passed is Phase 5's 58 new `tests/unit/test_domain_{scoring,costs,
tco,ranking}.py` tests. `pytest tests -q` with no container (`CARDINAL_DATABASE_URL` unset)
still passes 272 (37 skipped) — every P5 test is pure/deterministic and needs no database,
same as the rest of `src/domain`. Nothing regressed at any step; gate 5 itself needs no
container at all (all ten criteria are pure or deterministic code, D-015's reasoning applied
to P5).

The jump from 272 to 310 passed (both "no container" runs) is Phase 6's new
`tests/unit/test_ui_{validate,compiler,actions}.py` and `tests/integration/test_api_ui.py`,
net of `tests/unit/test_mcp_ui.py`'s five old P2 stub-pinning tests, which P6 rewrote entirely
to exercise the real compiler-backed handlers instead. Nothing regressed: every test that
existed before Phase 6 still passes unchanged.

The 3 skips (all runs) are `mock_autobazaar` sitting out three rental-only contract tests — a
dealer adapter has no rentable listings to price. They are selected on `adapter.kind`, never on
the adapter's name.

The 26 (30 from Phase 3, 34 from Phase 4) integration tests skip instead when
`CARDINAL_DATABASE_URL` is unset, so `make test` runs with no container — that accounts for the gap
between the container runs' 3 skipped and the no-container runs' 29 skipped. The jump from 107 to
133 passed between the second and third runs is Phase 2's 25 new `tests/unit/test_mcp_*` tests
landing; the jump from 133 to 232 in the fourth run is Phase 3's 66 new `tests/unit/test_agent_*`
tests plus 4 new Postgres-backed session-store tests; the jump from 232 to 248 in the fifth run is
Phase 4's 13 new `tests/unit/test_agent_journal.py` tests plus 4 new Postgres-backed decision-
journal tests (`tests/integration/test_agent_journal_postgres.py`), run with the container up.
Nothing regressed at any step.

### Environment notes

- Python 3.14 on Windows. `psycopg`'s async mode rejects the default `ProactorEventLoop`, so every
  database entry point goes through `run_async` in `src/adapters/db/session.py`, and the test suite
  selects a `SelectorEventLoop` via pytest-asyncio's `pytest_asyncio_loop_factories` hook. This
  does *not* cover `uvicorn src.api.main:app` run directly on native Windows (outside Docker) --
  uvicorn creates and owns its own event loop before any of our code runs, so `run_async` has
  nothing to wrap; discovered when Phase 8's gate spawned a real `uvicorn` subprocess that
  actually touched Postgres for the first time. `docker compose up`'s `api` container is Linux
  and unaffected; this only bites a bare `python -m uvicorn ...` on Windows against a live
  `CARDINAL_DATABASE_URL`, which no documented workflow (`make dev` included, in its usual
  `DEMO_MODE`/in-memory posture) currently exercises.
- `docker compose up` was verified cold, from a removed volume: alembic ran `0001_initial`, the seed
  wrote 240 rows, `/health` returned 200.
- `web/`'s toolchain: Node v24, npm. `@a2ui/react`'s published package nests its own copy of
  `@a2ui/web_core`; without `web/package.json`'s `"overrides": {"@a2ui/web_core": "0.9.1"}` a
  fresh `npm install` produces two type-incompatible copies (DECISIONS.md D-027). Playwright's
  Chromium build was already present on this machine (`npx playwright install chromium` is a
  no-op if so, otherwise a ~150 MB download) — gate 6.2 reports `PENDING` rather than failing
  when `web/node_modules` doesn't exist yet.

---

## Live path — first real rehearsal (2026-08-08)

The live orchestrator ran end-to-end against a real model for the first time, in a browser, with
`DEMO_MODE=false` and a real `ANTHROPIC_API_KEY`. This is the rehearsal every phase entry from
P3 onward listed as "deferred, deliberately" (D-015). It found four defects, all of them in code
that typechecked, passed 530 tests, and had never been executed:

| Defect | Fix | Recorded |
|---|---|---|
| No chat transport at all — `orchestrator.send()` had no HTTP route, and `web/` had no text input. `DEMO_MODE=false` rendered a blank page with nothing clickable. | `POST /sessions/{id}/messages` + a real composer in `web/src/App.tsx` | — |
| `prompts/` missing from the runtime image; `prompts.py` resolved it relative to a source checkout. Every live turn died at the first `load_prompt`. | Dockerfile copies `prompts/`; `PROMPTS_DIR` falls back to cwd | D-053 |
| A new `ClaudeSDKClient` per turn with a pinned session id — `Session ID ... is already in use` on every turn after the first, and no conversation memory even in principle. | One long-lived connected client per session, per-session lock | D-052 |
| The A2UI canvas stayed empty because the system prompt never told the model to render to it. | `prompts/orchestrator_system.md` now names when each `render_*` tool is expected | D-054 |

Also added, not a defect fix: assistant text and tool activity now stream to the browser over
the existing SSE channel as the turn runs (`agent_text`/`agent_status`, discriminated the same
way `mcp_app_open` already is), because a live turn takes tens of seconds and a static spinner
for that long is indistinguishable from a hang.

Two more defects surfaced only once a browser drove the deployed image, both invisible to curl:

| Defect | Fix | Recorded |
|---|---|---|
| nginx's 60s default `proxy_read_timeout` cut off a ~72s turn as a 504. The UI showed a failed message while the backend answered fine seconds later. Direct `curl` to `:8000` bypassed nginx and never saw it. | `proxy_read_timeout 300s` on `/sessions/` in `web/nginx.conf` | — |
| Every subagent's traffic streams through `receive_response()`, including the `UserMessage` carrying the prompt it was launched with — so the `interviewer`'s system prompt was published into the chat rail as if the agent had said it. | `_progress_events`/`_extract_assistant_text` now take text only from top-level `AssistantMessage`s (`parent_tool_use_id is None`) | — |

**Model routing is now env-selectable and defaults to the cheap tier** (D-055).
`CARDINAL_AGENT_MODEL` / `_EFFORT` / `_THINKING` default to `claude-haiku-4-5` / `low` /
`disabled`; PLAN-00 §6.7's `claude-opus-5` / `high` / `adaptive` is one uncommented block in
`.env`. Measured on the same INTERVIEW turn: **~72s on the plan's routing, ~5s on the default.**

The weaker default model is also a better prompt test than the strong one, and it earned its
keep immediately: it skipped the `render_*` canvas tools Opus called unprompted, and it narrated
its own delegation ("I've launched the interviewer") instead of asking the questions. Both were
unstated expectations in `prompts/orchestrator_system.md` — now stated (D-055's closing note).

`DEMO_MODE` was removed from the product UI in the same pass — there is one real path now, not a
demo path plus a live path. `POST /demo/{id}/start` still exists and is still gated on
`DEMO_MODE=true`; nothing in `web/` calls it.

---

## Alternate INTERVIEW-phase models + a full re-proof of the demo path (2026-08-08)

**Model selection (D-056).** `GET /models` + `POST /sessions/{id}/model` let a session pick
Groq/Gemini/OpenRouter/OpenAI for the INTERVIEW phase's conversational Q&A only —
`src/agent/providers.py` (plain `httpx`, no SDK) + `src/agent/interview_chat.py` (one call per
turn, folded through the existing `process_turn` so phase-transition logic is unchanged). The
moment `Phase` advances past INTERVIEW, the session falls through to the untouched
`CardinalOrchestrator.send()` — every MCP tool, every subagent, every guardrail, `confirm_booking`'s
invisibility, all exactly as before — primed once with what the alternate model already gathered.
Verified live end-to-end against Groq's free tier (zero Anthropic spend): correct slot extraction,
correct hand-off, RESEARCH starting with the right numbers and no re-asked questions. Reasoning
models (Qwen) need `<think>` stripped before their JSON parses — the same fix
`D:\Interview Agent`'s own `llm_router.py` already carries for the identical failure.

**Re-proving the demo path found two packaging bugs older than this session (D-057).** Asked to
show the PowertrainExplainer 3D view and the checkout/payment gateway working, `demo-e2e.spec.ts`
(gate 11.3/11.4) failed on beats it had never failed on before:

| Defect | Fix |
|---|---|
| The new `GET /models` route's nginx location was a *prefix* match, so it also swallowed the older, unrelated static path `/models/powertrain/*.glb` into a 404 — `<model-viewer>` had nothing to load and rendered as a silent empty box. | `location = /models` (exact match) in `nginx.conf`; equivalent `bypass` fix in `vite.config.ts`'s dev proxy |
| `booking-mcp`'s static resource HTML (`booking_form.html`, `checkout.html`) was never declared as package data, so `pip install .` silently dropped it — same category of bug as D-053's `prompts/`, first caught here because this was the first time `resources/read` ran against the *installed* package rather than a checkout. | `[tool.setuptools.package-data]` in `pyproject.toml` |

Gate 11 re-run clean after both fixes: **8 passed, 0 failed, 3 pending** (11.8 needs a human,
11.9 needs a recorded video, 11.11 is `[SCALE]`) — all seven demo beats, including the 3D viewer
and the sandboxed checkout with its financing calculator and mock-payment banner, screenshotted
fresh under `docs/screenshots/`. `demo-e2e.spec.ts`'s beat-1 trigger was updated from clicking the
now-removed "Start Demo" button to a direct `POST /demo/{id}/start` call, matching D-055's UI
redesign rather than reverting it.

---

## Qwen as the default interview model, per-listing 3D, and a real demo script (2026-08-08)

**Model picker is now hidden by default; Qwen 3.6 (Groq, free) is the INTERVIEW-phase default**
(D-059). `CardinalOrchestrator.model_for` resolves `CARDINAL_INTERVIEW_MODEL` (default
`groq/qwen/qwen3.6-27b`) instead of hardcoding Claude; `GET /models` returns `[]` unless
`CARDINAL_SHOW_MODEL_PICKER=true`, and `App.tsx`'s existing `models.length > 1` guard means the
picker UI needed no code change to disappear — one backend flag, not two switches to keep in sync.
Two real bugs fell out of scripting real conversational turns against Qwen rather than
hand-fed JSON (D-058): no anchor for "today" (a relative-date turn burned its whole token
budget deliberating inside an unclosed `<think>` block and returned nothing), and `<think>`
stripping alone can't recover text that was never emitted — `providers.chat` now passes Groq's
`reasoning_format="hidden"` for any model `model_catalog` flags `reasoning: True`, which keeps
the chain of thought out of `content` structurally rather than filtering it after the fact.

**Per-listing 3D on result cards** (D-060), distinct from P6's per-archetype
`PowertrainExplainer`: `src/mcp/ui/vehicle_models.py`'s three-tier resolver (real per-vehicle
GLB → body-style silhouette → powertrain cutaway, always resolves to *something*) feeds a new
`CardVisual` the `render_results` handler attaches per listing, kept out of the compiler itself
(PHASE-6 SS4's purity constraint) the same way `render_detail`'s headline already is. 28 cars in
`VEHICLE_SLUGS` were derived, not guessed — verified as exactly what the demo script's eight
scripted openers put on screen against the real seeded store, not assumed from catalogue
frequency (the most-listed models in the seed are largely unfindable as downloadable 3D
assets). None are sourced yet (`scripts/check_vehicle_assets.py` reports 0/28); every card
degrades to a real, present, placeholder-cube silhouette (`scripts/generate_silhouette_assets.py`,
12/12 present) rather than an empty box, so the feature is fully functional today and sourcing
real models is purely additive.

**`docs/DEMO-SCRIPT.md`** is what to actually say to the product: a five-minute guided run plus
eight alternate openers, each pinned to real listings/prices from the seeded catalogue (not
illustrative numbers), a 3D-asset sourcing guide with the exact 28-car table and a licensing/size-
budget note (gate 6.7's 16 MB cap means every sourced model needs decimating — a raw download
does not fit), and two known-fixed edge cases (a relative-date turn, an impossible ask) worth
demonstrating deliberately.

**Full re-verification after all of the above:** lint/typecheck/571 tests green, frontend build
clean, gate 6 green (9/9 + 1 `[SCALE]` pending), gate 11 green (8/8 + 3 pending, none new),
`.env.example` gate (11.7) now covers `CARDINAL_INTERVIEW_MODEL`/`CARDINAL_SHOW_MODEL_PICKER`
too. Live-confirmed: `GET /models` → `[]`, a plain interview turn on the Groq default responds
in ~3s with no picker, no leaked model name, and no cost beyond Groq's free tier.

---

## RESEARCH never advanced in the live path (2026-08-08)

**A real bug, reported live, reproduced, fixed, only partially re-confirmed (D-062).** The
handoff-primed live path (Groq INTERVIEW → Claude RESEARCH) got stuck after "searching both
marketplaces..." with no results ever rendering. Cause: `phase_machine.advance()` -- what moves
`Phase` from RESEARCH to RECOMMEND once candidates exist -- was never called anywhere in the
live path; `demo.py`/`demo_stream.py` drive it procedurally for their scripted paths, but
`orchestrator.py`'s `send()` had no equivalent. The live model correctly never called
`render_results` (its own prompt reserves that for RECOMMEND), because nothing ever told its
phase context RESEARCH was done. Fixed with `build_phase_advance_hook`, a `PostToolUse` hook
mirroring the existing `PreToolUse` audit hook's pattern.

**The first two versions of that fix were both wrong (D-066).** Each guessed at the shape of
`PostToolUse`'s `tool_response` and each silently extracted nothing from searches that had
really found cars — the same empty canvas, now caused by the fix rather than its absence. With
the Anthropic cap blocking a third live attempt, the shape was instead read straight out of the
bundled CLI binary (`grep -a` over `claude.exe`), which builds the payload itself:
`tool_response` is the tool_result block's **`content`** — for an MCP tool, a *bare list* of
content blocks, not a dict wrapping a `content` key. Both earlier versions keyed off the dict
form, so a bare list fell through and returned nothing every time.

**And the parser was not the last of it (D-067).** With credits restored, the first real
rehearsal found three more defects stacked behind each other, none visible from a source
checkout, each uncovered by *printing what the live path actually did* rather than reasoning
about it:

| # | Defect | Fix |
|---|---|---|
| 1 | Guardrails matched bare tool names; live tools arrive namespaced (`mcp__market__search_cars`). The phase hook, the audit hook's denial, and gate 3.8's backstop all silently never matched. | `base_tool_name()` normalises — the same `rsplit` `_progress_events` already did |
| 2 | The prompt told the orchestrator to delegate searching to two `researcher` subagents; the `Agent` tool launched them **asynchronously** and the turn ended before any had searched. The person was answered before a result existed. | Prompt now calls `search_cars` directly and waits (it already queries every marketplace, D-013); the hook is replaced by `extract_candidate_ids`, a scan of the finished turn's message stream |
| 3 | The audit hook looked state up by the **CLI's** session id, not the app's — so `_filled_required_count` always read 0. Latent forever; fix (1) *activated* it, and it then blocked every live search with "no RequirementProfile has been started". | Bind the app `session_id` up front, exactly as `build_search_gate` always did |

**Verified live, end to end — the thing outstanding since D-015.** A real session now runs
INTERVIEW (Groq) → handoff → RESEARCH (Claude) → phase advances to `recommend` with 7 real
candidates → **7 `CarCard`s render on the canvas** with real scores and rationales (a 2024
Toyota RAV4 GT-Line at €23,003.83, score 9.20, citing its €6,996 budget headroom), zero page
errors. Screenshotted; gate 3 green.

Worth carrying forward: fix (1) *created* symptom (3) — unblocking one guardrail activated
another that had never run. Changes in this layer need re-verifying live, not assuming.

RECOMMEND → TRANSACT may still have the same shape of gap (`selected_candidate` in the live
path) — now testable, not yet exercised.

---

## Next

Every `[MVP]` line in every phase, including Phase 11, is now green — `docker compose up` on a
clean-ish machine (untouched `.env.example`) brings up the full four-service stack and the whole
seven-beat demo runs with zero API keys. What's left is the `[SCALE]` backlog (deferred per
CONSTITUTION III.3, none of it blocking) and the handful of things only a human, a live model, or
a second machine can actually do:

1. **Record the demo video** (`docs/VIDEO-SCRIPT.md`'s shot list, gate 11.9's other half) and
   **run gate 11.8 for real** — a person who didn't write this repo, on a machine that's never
   seen it, following `README.md`'s Run It section verbatim. Both are structurally impossible for
   this session to complete itself; everything mechanical gate 11 could stand in for, it does.
2. **A live rehearsal of `src/agent/orchestrator.py`** against the real `claude` CLI, with
   `ANTHROPIC_API_KEY` set, at least once — the wiring is real and type-checked but has only been
   exercised through `DEMO_MODE`'s deterministic path so far (DECISIONS.md D-015). This should
   be the first time a live session calls `rank()` with a model-chosen `WeightSet`, the first
   time `render_results`/`compose_surface`/`open_booking_form`/`open_checkout` are called from
   inside a real conversation rather than a gate script or test, the first time a judge's own
   trusted click — not Playwright's simulated one — reaches `confirm_booking`, and the first
   time `ClaudeAgentSDKInstrumentor`'s auto-generated spans and a real Langfuse export
   (`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`) get exercised outside `src/agent/tracing.py`'s
   own unit tests.
3. **Phase 8's own deferred items** — a real `PaymentGateway` behind the mock's protocol seam
   (feature-flagged, `[SCALE]`), refund/cancellation tool surfaces for the `CANCEL`/`ABANDON`
   transitions the state machine already supports, and the native-Windows `uvicorn`+Postgres
   event-loop gap noted above (Docker-only impact today).
4. **Phase 9's `[SCALE]` tier** — prompt-cache hit-rate tracking (gate 9.8), CI-gated eval
   regression detection (gate 9.9), per-session cost budget + hard cap, the reasoning-replay
   timeline in-product, online evals on sampled real sessions — deferred per CONSTITUTION
   III.3; all need a live session to threaten a budget or produce a cache signal against.
5. **Phase 5's `[SCALE]` tier** — constraint relaxation / counterfactuals on infeasibility
   (gate 5.10), weight calibration against outcome data, regional tax/insurance/energy tables —
   deferred per CONSTITUTION III.3.
6. **Phase 6's `[SCALE]` tier** — `Vehicle360`, progressive/streaming render, reduced-motion +
   full a11y pass (gate 6.10), real `PowertrainExplainer` geometry to replace the placeholder
   GLBs (D-028) — deferred per CONSTITUTION III.3.
7. **Phase 4's `[SCALE]` tier (4.4-4.8)** — episodic memory, semantic/pgvector retrieval,
   consolidation/contradiction/staleness, drift detection, `forget_me` — deferred per
   CONSTITUTION III.3 (DECISIONS.md D-019). `forget_me` (gate 4.8) now also needs to erase
   from Langfuse, per IV.3 -- P9 gives it somewhere real to erase from. This is now the only
   remaining `[SCALE]` backfill target that isn't Phase 10's own (item 9 below) or Phase 9's
   (item 4 above) — the episodic-memory tier gate 10.2/10.5 both currently lean on being
   correctly unbuilt.
8. Keep `specs/{spec,plan,tasks}.md` current as phases land — CONSTITUTION V (spec-kit
   governance) treats them as living artifacts, not a one-time exercise. `PROGRESS.md` stays the
   sole source of truth for status either way.
9. **Phase 10's `[SCALE]` tier** — PII redaction for logs + the memory tier (gate 10.5, half
   already done via P9's gate 9.6), two-tenant isolation (gate 10.6, a schema migration once
   a second tenant is real), `pip-audit`/`npm audit` in CI (gate 10.7), `docs/ATTRIBUTION.md`
   (gate 10.8, nothing to attribute until P6's placeholder GLBs are replaced), and
   `docs/THREAT-MODEL.md` as a standalone gated file (gate 10.9, the content already exists
   in `plans/PHASE-10-TRUST.md` §8) — deferred per CONSTITUTION III.3.
10. **Phase 11's `[SCALE]` tier** — a public deployment (gate 11.11), CI/CD with image
    publishing so `make verify`/gate 11 run on every push instead of only locally, and
    `docs/ARCHITECTURE.md` + an ADR index + a contributor guide (the content exists today,
    split across the README, `plans/PLAN-00-OVERVIEW.md`, and `DECISIONS.md`; none of it is
    indexed as those specific artifacts yet) — deferred per CONSTITUTION III.3.
