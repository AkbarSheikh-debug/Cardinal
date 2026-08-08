/**
 * Gate 11 (PHASE-11-DELIVERY.md SS7, criteria 11.3/11.4): walks the real product -- the actual
 * `index.html` app, not `mcp-host-harness.html` -- through all seven demo beats PHASE-11 SS6
 * lists for the video, screenshotting each. Everything rendered here came from a real backend
 * call: `POST /demo/{session}/start` drives `src/agent/demo_stream.py`'s scripted persona
 * through the real phase machine, P5 ranking/critic pass and P1 TCO engine, pushing real A2UI
 * messages over the same SSE transport a live session uses (PHASE-6 SS6). The booking form and
 * checkout are the real MCP Apps (PHASE-7) behind the real cross-origin sandbox -- this test
 * fills them and clicks through for real, the same double-iframe mechanism gate 7/8's own specs
 * already prove, just reached by clicking "Start Demo" instead of `mcp-host-harness.html`'s
 * query-param mount.
 *
 * `scripts/gate_phase11.py` starts the backend itself with an environment scrubbed down to just
 * `DEMO_MODE=true` (gate 11.4's own evidence) before running this file, the same
 * disposable-backend-on-a-dedicated-port pattern gates 7/8 already use for the same reason
 * (D-013's note on gate 7.7: a `docker compose up` left running from earlier must never be
 * mistaken for this run's own backend).
 */
import { test, expect, type Page, type Frame, type Locator } from "@playwright/test";

// No `@types/node` dependency in this project (commerce.spec.ts's own note) -- resolved
// relative to `web/` (this suite's cwd, `scripts/gate_phase11.py` runs `npx playwright test`
// from there), a sibling of `web/`, so no `node:path`/`node:fs` import is needed. The
// directory is created ahead of time (not by this file) since Playwright's `screenshot({path})`
// does not reliably create missing parent directories on every platform.
const SCREENSHOT_DIR = "../docs/screenshots";

// Each new surface is *appended* to the canvas (PHASE-6 SS6: create-once-then-update, never
// re-laid-out), so by beat 4 the page is taller than one viewport and a plain viewport
// screenshot silently shows whatever was on-screen from an *earlier* beat -- a real bug this
// spec's first draft had, where beats 4b/5 were byte-identical to beat 4. Scrolling the beat's
// own new element into view first is what makes each screenshot actually show that beat.
function shot(page: Page, name: string, focus?: Locator): Promise<void> {
  return (focus ? focus.scrollIntoViewIfNeeded() : Promise.resolve())
    .then(() => page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png` }))
    .then(() => undefined);
}

async function waitForFrame(
  page: Page,
  predicate: (frame: Frame) => boolean | Promise<boolean>,
  timeoutMs = 15_000,
): Promise<Frame> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    for (const frame of page.frames()) {
      if (await Promise.resolve(predicate(frame)).catch(() => false)) return frame;
    }
    await page.waitForTimeout(150);
  }
  throw new Error(`no matching frame within ${timeoutMs}ms (frames: ${page.frames().map((f) => f.url()).join(", ")})`);
}

async function waitForBlobFrameWithSelector(page: Page, selector: string): Promise<Frame> {
  return waitForFrame(page, async (frame) => {
    if (!/^blob:/.test(frame.url())) return false;
    return (await frame.locator(selector).count()) > 0;
  });
}

test.describe.configure({ mode: "serial" });

test("11.3/11.4 walks all seven demo beats end to end, screenshotting each", async ({ page }) => {
  const session = `demo-e2e-${Date.now()}`;

  await page.goto(`/?session=${encodeURIComponent(session)}`);

  // D-056/D-057: the model-selection redesign removed the "Start Demo" button from the live
  // product UI (the user's own call -- one real path, not a demo path plus a live path). The
  // scripted flow this test proves out is still real and still reachable, just no longer via a
  // click: `POST /demo/{id}/start` is the same route `App.tsx`'s old button used to call.
  const start = await page.request.post(`/demo/${session}/start`);
  expect(start.ok()).toBe(true);

  // -- Beat 1: interview progress ----------------------------------------------------------
  const progress = page.locator(".cardinal-interview-progress");
  await expect(progress).toBeVisible({ timeout: 15_000 });
  await expect(progress.locator("li[data-status='filled']").first()).toBeVisible({ timeout: 15_000 });
  await shot(page, "beat-1-interview-progress", progress);

  // -- Beat 2: rent-vs-buy break-even (real P5 TCO engine) -----------------------------------
  const tco = page.locator(".cardinal-tco-chart");
  await expect(tco).toBeVisible({ timeout: 15_000 });
  await shot(page, "beat-2-rent-vs-buy-breakeven", tco);

  // -- Beat 2b: the itemised cost radar (D-061) -- a real click dispatches `expand_tco`
  // (PHASE-6 SS6's action round-trip), which `demo_stream.handle_expand_tco_action` answers
  // with the same `TcoComparison` beat 2 already computed (D-026's no-recomputation rule).
  await tco.locator(".cardinal-tco-expand").click();
  const radar = page.locator(".cardinal-tco-radar");
  await expect(radar).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".cardinal-tco-radar-poly")).toHaveCount(2);
  await shot(page, "beat-2b-tco-radar-expanded", tco);

  // -- Beat 3: parallel research -- the progress surface updates in place (gate 6.6), not a
  // new surface, so this asserts its *content* changed rather than looking for a new element.
  await expect(progress.locator(".cardinal-reasoning-trace")).toContainText("searching", {
    timeout: 15_000,
  });
  await shot(page, "beat-3-parallel-research", progress);

  // -- Beat 4: ranked results, real scoring + critic pass ------------------------------------
  const cards = page.locator(".cardinal-car-card");
  await expect(cards.first()).toBeVisible({ timeout: 15_000 });
  await shot(page, "beat-4-ranked-results", cards.first());

  // The must-land moment: opening a score breakdown. A real click dispatches a real `explain`
  // action (PHASE-6 SS6's round-trip); the backend answers with the real ScoreBreakdown
  // `rank()` already computed (D-026, no recomputation).
  await cards.first().click();
  const breakdown = page.locator(".cardinal-score-breakdown");
  await expect(breakdown).toBeVisible({ timeout: 10_000 });
  await expect(breakdown.locator(".cardinal-criterion-bar").first()).toBeVisible();
  await shot(page, "beat-4b-score-breakdown-opened", breakdown);

  // -- Beat 5: powertrain explainer for the winning candidate --------------------------------
  const explainer = page.locator(".cardinal-powertrain-explainer");
  await expect(explainer).toBeVisible({ timeout: 15_000 });
  await shot(page, "beat-5-powertrain-explainer", explainer);

  // -- Beat 6: booking App -- a real MCP App, real cross-origin sandbox (PHASE-7) ------------
  const host = page.getByTestId("mcp-app-host");
  await expect(host).toBeVisible({ timeout: 15_000 });
  const bookingFrame = await waitForBlobFrameWithSelector(page, "#form-root");
  await bookingFrame.locator("#form-root").waitFor({ state: "visible", timeout: 10_000 });
  await shot(page, "beat-6-booking-app-opened", host);

  await bookingFrame.locator("#name").fill("Jane Doe");
  await bookingFrame.locator("#email").fill("jane@example.com");
  await bookingFrame.locator("#collection_location").fill("Berlin");
  await shot(page, "beat-6b-booking-form-filled", host);

  // A real click on the App's own submit button -- not something this test's own backend call
  // performed; `demo_stream.on_draft_submitted` (src/api/main.py) reacts to this exact RPC.
  await bookingFrame.locator("#submit-button").click();
  await expect(bookingFrame.locator("#status")).toContainText("submitted", { timeout: 10_000 });

  // -- Beat 7: mock checkout -- opened only after the real submit above, priced fresh --------
  const checkoutFrame = await waitForBlobFrameWithSelector(page, "#pay-button");
  await checkoutFrame.locator("#form-root").waitFor({ state: "visible", timeout: 10_000 });
  const banner = checkoutFrame.locator("#mock-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("MOCK");
  await shot(page, "beat-7-checkout-opened", host);

  // The other must-land moment: the agent cannot press Confirm. Everything up to and including
  // this click is a real, `isTrusted` browser event -- no agent code anywhere in this repo
  // calls `mint_gesture_token` or `confirm_booking` (gate 8.3's own assertion, exercised here
  // by an actual person-shaped click rather than restated as a unit test).
  await checkoutFrame.locator("#card_name").fill("Jane Doe");
  await checkoutFrame.locator("#card_number").fill("4242 4242 4242 4242");
  await checkoutFrame.locator("#card_expiry").fill("12/30");
  await checkoutFrame.locator("#card_cvc").fill("123");
  await checkoutFrame.locator("#pay-button").click();
  const status = checkoutFrame.locator("#status");
  await expect(status).toHaveAttribute("data-outcome", "success", { timeout: 15_000 });
  await shot(page, "beat-7b-checkout-confirmed", host);

  // -- Trace: the RPC audit log this whole flow left behind (PHASE-7 SS5.5) -- concrete
  // evidence of spec compliance, the slide P11's own deck singles out.
  const audit = await page.request.get(`/mcp-apps/${session}/audit`);
  expect(audit.ok()).toBe(true);
  const auditEntries = (await audit.json()) as unknown[];
  expect(auditEntries.length).toBeGreaterThan(0);
  await shot(page, "beat-8-trace-and-audit-log");
});
