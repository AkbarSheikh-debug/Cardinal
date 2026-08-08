# Demo video script

**Not yet recorded.** This is the shot list for the 3–4 minute video PHASE-11 §6 asks for —
recording it (screen capture + narration) is a human step this repository's tooling can't stand
in for. `web/tests/demo-e2e.spec.ts` walks the identical sequence headlessly and screenshots each
beat under `docs/screenshots/` (gate 11.3), so every shot below has already been proven to render
for real before anyone points a screen recorder at it.

**Record in `DEMO_MODE`** (`docker compose up` with `.env.example`'s defaults — no API keys, no
live-latency risk) so the recording is reproducible and never depends on model response time
(PHASE-11 §6, gate 11.4's own reasoning).

**Since D-063, the app narrates itself.** `demo_stream.py` pushes both sides of the scripted
conversation to the chat rail now, not just canvas updates — the "Say" column below is what the
*presenter* adds on top for context a chat bubble can't carry (why something matters, not what
just happened), not a transcript to read verbatim over a silent UI.

## Setup

1. `docker compose up --build`, wait for all four services healthy.
2. Open `http://localhost:5173/?session=<pick-a-name>` in a clean browser window (no extensions,
   no dev tools visible) — the URL's `?session=` is what names this run; reusing one that already
   played back just replies "already-running" and does nothing.
3. From a terminal (kept off-screen, or trigger it moments before recording starts):
   `curl -X POST http://localhost:8000/demo/<same-name>/start`. There is no in-app button for
   this — the product's single real chat path replaced the old "Start Demo" button, so this one
   API call is what a presenter (or a second window) triggers instead.
4. Have `docs/screenshots/` open in a second window as a fallback reference for framing each shot.

## Shots

| # | Beat | What's on screen | Say |
|---|---|---|---|
| 1 | Cold open | Empty canvas, chat rail empty | "Cardinal is an advisor, not a filter. Watch what it does with one sentence." |
| 2 | Trigger the run (off-screen `curl`, or cut in) | First chat bubble appears on its own | (silent beat — let the UI start moving) |
| 3 | Interview progress | Chat rail shows the scripted back-and-forth; canvas's `InterviewProgress` surface fills in alongside it | "It elicits the requirements a search box never asks for — and the state is code-owned, not a paragraph the model has to remember." |
| 4 | Rent-vs-buy break-even | `TcoChart` with a break-even month, Cardinal's own line calling out the number | "This is arithmetic most buyers can't do in their head — a real total-cost-of-ownership curve, not an estimate." |
| 5 | Parallel research | Progress surface updates: "searching mock_autobazaar and mock_drivenow in parallel…" | "Two marketplaces researched concurrently — the trace will show these as genuinely overlapping spans, not sequential calls dressed up." |
| 6 | Ranked results | `CarCard` list appears, ranked, staggered entry animation | "Every candidate is scored, not vibes-ranked." |
| 7 | **Click a card → score breakdown opens** | `ScoreBreakdown` stacked bars, spring-fill animation | **Must-land moment #1.** "Click any result and the exact weighted breakdown that produced its rank opens — the model chose the weights, this code computed the score. Ask 'why #1 over #2' and there's a number, not a paragraph." |
| 7b | Click **"See itemised cost breakdown →"** on the TCO card | Radar chart appears, one polygon per path | "And the same is true of the finance — this isn't a single number, it's a per-category comparison." |
| 8 | Powertrain explainer | 3D cutaway with hotspot annotations | "And when the engine matters to the decision — a timing belt means a service interval, a BEV skateboard has no transmission to fail — it explains that visually, not decoratively." |
| 9 | Booking App opens | Sandboxed iframe, booking form slides in | "The booking form isn't a link out — it's rendered *inside* the conversation, as a real MCP App, cross-origin sandboxed from the host page." |
| 10 | Fill and submit the form | Name/email/city entered, Submit clicked | (narrate briefly while filling) "Every field here is a real, isolated iframe — the host never sees what's typed until the form submits it." |
| 11 | Checkout opens | `MOCK — NO REAL PAYMENT` banner visible above the fold | "Checkout opens automatically — priced fresh, server-side, from the same quote engine as the search results. And yes, that banner is unconditional, not a footnote." |
| 12 | Fill test card, click **Authorize Transaction** | Card fields filled, button pressed | (narrate) "This is the moment that matters most." |
| 13 | **Confirm succeeds via a real click** | Status flips to a success state, the confirm ring animates | **Must-land moment #2.** "Nowhere in this codebase can the agent press this button. `confirm_booking` isn't hidden by a prompt — it's structurally absent from the model's own tool list. The only thing that can reach it is a trusted click carrying a single-use token minted at that click. This is the trust story, not a feature." |
| 14 | Trace / audit log | `GET /mcp-apps/{session}/audit` (or a terminal `curl`) showing one entry per RPC | "Every one of those clicks left an audit entry — a compliance reviewer's evidence, not a claim." |
| 15 | Close | Cardinal wordmark or the architecture diagram from the README | "Cardinal: an advisor with the receipts." |

## Timing

Aim for ~15–20 seconds per shot; shots 7 and 13 (the two must-land moments) are the only ones
worth lingering on — 5–8 seconds of silence after each so the point actually registers.

## Recording checklist

- [ ] `docker compose up --build` from a clean `docker compose down` (not `-v` — keep the seeded
      volume so this is repeatable)
- [ ] Browser zoom at 100%, window sized so no scrollbars appear mid-recording
- [ ] Narration recorded separately and mixed in post, or read live from this table
- [ ] Export at 1080p, ≤4 minutes, saved as `docs/cardinal-demo.mp4`
- [ ] Re-run `python -m scripts.gate_phase11` afterward — 11.9 turns from PENDING to PASS once
      the file exists
