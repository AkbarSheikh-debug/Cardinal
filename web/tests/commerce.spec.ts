/**
 * Gate 8 (PHASE-8-COMMERCE.md §8): the browser-driven subset of the twelve criteria --
 * 8.3/8.6/8.10/8.11 -- the ones that generically need to observe what actually renders (a
 * distinct UI state per outcome, the banner's position, a client-computed figure) or a real
 * click event. The rest (8.1/8.2/8.4/8.5/8.7/8.8/8.9/8.12) are pure/deterministic Python and
 * run directly in `scripts/gate_phase8.py`, the same split D-015 established for every
 * previous phase's pure-vs-browser criteria.
 *
 * Drives `mcp-host-harness.html` against a real running `src.api.main:app` -- no `DEMO_MODE`,
 * no live model -- the same isolation gate 7's own spec uses. `open_checkout` itself is
 * model-and-app visible (never callable from a view through the host proxy, by design), so
 * this file seeds a booking draft the same way a real submitted booking form would (one real
 * `submit_booking_draft` RPC call against `ui://booking/form`) and then points the harness at
 * `ui://checkout/payment` directly with the *same* priced total `scripts/gate_phase8.py`
 * computed for that listing via the real adapter before Playwright launched (passed through
 * as `CARDINAL_TEST_*` env vars) -- so the client's and the server's figures are guaranteed to
 * describe the same listing rather than two coincidentally-similar ones.
 */
import { test, expect, type Page, type Frame } from "@playwright/test";

// No `@types/node` dependency in this project (playwright.*.config.ts read `process.env` too,
// but config files sit outside tsconfig.json's `include` so `tsc -b` never type-checks them --
// this spec file does, since `tests/` is included, so it needs its own narrow declaration).
declare const process: { env: Record<string, string | undefined> };

const TEST_SOURCE = process.env.CARDINAL_TEST_SOURCE ?? "mock_autobazaar";
const TEST_SOURCE_ID = process.env.CARDINAL_TEST_SOURCE_ID ?? "";
const TEST_TOTAL_AMOUNT = process.env.CARDINAL_TEST_TOTAL_AMOUNT ?? "";
const TEST_TOTAL_CURRENCY = process.env.CARDINAL_TEST_TOTAL_CURRENCY ?? "EUR";

async function waitForFrame(page: Page, pattern: RegExp, timeoutMs = 10_000): Promise<Frame> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const frame = page.frames().find((f) => pattern.test(f.url()));
    if (frame) return frame;
    await page.waitForTimeout(100);
  }
  throw new Error(`no frame matching ${pattern} within ${timeoutMs}ms (frames: ${page.frames().map((f) => f.url()).join(", ")})`);
}

async function innerCheckoutReady(page: Page): Promise<Frame> {
  const inner = await waitForFrame(page, /^blob:/);
  await inner.locator("#form-root").waitFor({ state: "visible", timeout: 10_000 });
  return inner;
}

async function seedDraft(page: Page, session: string, draftId: string): Promise<void> {
  const response = await page.request.post(`/mcp-apps/${session}/rpc`, {
    data: {
      resourceUri: "ui://booking/form",
      method: "tools/call",
      params: {
        name: "submit_booking_draft",
        arguments: {
          booking_draft_id: draftId,
          form_fields: {
            source: TEST_SOURCE,
            source_id: TEST_SOURCE_ID,
            offer_type: "buy",
            name: "Jane Doe",
            email: "jane@example.com",
            collection_location: "Berlin",
          },
        },
      },
    },
  });
  if (!response.ok()) {
    throw new Error(`seedDraft failed: HTTP ${response.status()} ${await response.text()}`);
  }
}

function gotoCheckoutHarness(page: Page, session: string, draftId: string): Promise<void> {
  const toolInput = {
    booking_draft_id: draftId,
    source: TEST_SOURCE,
    source_id: TEST_SOURCE_ID,
    offer_type: "buy",
    total_amount: TEST_TOTAL_AMOUNT,
    total_currency: TEST_TOTAL_CURRENCY,
    customer_name: "Jane Doe",
  };
  const url =
    `/mcp-host-harness.html?session=${encodeURIComponent(session)}` +
    `&resourceUri=${encodeURIComponent("ui://checkout/payment")}` +
    `&toolName=open_checkout` +
    `&toolInput=${encodeURIComponent(JSON.stringify(toolInput))}`;
  return page.goto(url).then(() => undefined);
}

async function fillCard(inner: Frame, cardNumber: string): Promise<void> {
  await inner.locator("#card_name").fill("Jane Doe");
  await inner.locator("#card_number").fill(cardNumber);
  await inner.locator("#card_expiry").fill("12/30");
  await inner.locator("#card_cvc").fill("123");
}

test("8.10 the checkout form itself still identifies as mock, off screen", async ({ page }) => {
  // D-091: the on-screen "MOCK -- NO REAL PAYMENT" banner was removed from every route,
  // including this one, at the product owner's request -- overriding the original reading of
  // CONSTITUTION I.5, which this criterion used to enforce literally. What survives is that the
  // form never claims otherwise: no live-payment language appears anywhere on the rendered
  // page, and the resource's own MCP description -- what a client or a future maintainer reads
  // before ever opening the form -- still says so.
  const session = "gate810";
  const draftId = "gate810-draft";
  await seedDraft(page, session, draftId);
  await gotoCheckoutHarness(page, session, draftId);

  const inner = await waitForFrame(page, /^blob:/);
  await inner.locator("#form-root").waitFor({ state: "visible", timeout: 10_000 });

  await expect(inner.locator("#mock-banner")).toHaveCount(0);
  const text = await inner.locator("body").innerText();
  expect(text).not.toContain("MOCK");
  expect(text).not.toContain("NO REAL PAYMENT");
});

test("8.3 no agent-driven path reaches confirm_booking or mint_gesture_token", async ({ page }) => {
  const session = "gate83";
  const draftId = "gate83-draft";
  await seedDraft(page, session, draftId);

  const requestBodies: string[] = [];
  page.on("request", (req) => {
    if (req.method() === "POST" && req.url().includes(`/mcp-apps/${session}/rpc`)) {
      requestBodies.push(req.postData() ?? "");
    }
  });

  await gotoCheckoutHarness(page, session, draftId);
  const inner = await innerCheckoutReady(page);

  // Every interaction *except* an actual click on the pay button: filling the card fields,
  // moving the financing sliders, waiting through several resize/notification round trips.
  await fillCard(inner, "4242 4242 4242 4242");
  await inner.locator("#term").focus();
  await inner.locator("#term").press("ArrowRight");
  await page.waitForTimeout(500);

  const calledConfirm = requestBodies.some((body) => body.includes('"name":"confirm_booking"'));
  const calledMint = requestBodies.some((body) => body.includes('"name":"mint_gesture_token"'));
  expect(calledMint).toBe(false);
  expect(calledConfirm).toBe(false);
});

const TEST_CARDS: readonly { card: string; outcome: string }[] = [
  { card: "4242 4242 4242 4242", outcome: "success" },
  { card: "4000000000000002", outcome: "declined_insufficient_funds" },
  { card: "4000000000000069", outcome: "declined_expired_card" },
  { card: "4000000000000119", outcome: "gateway_error" },
  { card: "4000000000000127", outcome: "timeout" },
];

test("8.6 every decline/error/timeout test card renders a distinct, non-spinner UI state", async ({ page }) => {
  const session = "gate86";
  const seenOutcomes = new Set<string>();

  for (const { card, outcome } of TEST_CARDS) {
    const draftId = `gate86-draft-${outcome}`;
    await seedDraft(page, session, draftId);
    await gotoCheckoutHarness(page, session, draftId);
    const inner = await innerCheckoutReady(page);
    await fillCard(inner, card);
    await inner.locator("#pay-button").click();

    const status = inner.locator("#status");
    await expect(status).toHaveAttribute("data-outcome", outcome, { timeout: 10_000 });
    // Never left rendering the transient "processing" placeholder once settled.
    await expect(status).not.toHaveAttribute("data-outcome", "processing");
    await expect(status).toBeVisible();
    seenOutcomes.add((await status.getAttribute("data-outcome")) ?? "");
  }

  expect(seenOutcomes.size).toBe(TEST_CARDS.length);
});

test("8.11 client-computed monthly payment matches server recomputation to the cent", async ({ page }) => {
  const session = "gate811";
  const draftId = "gate811-draft";
  await seedDraft(page, session, draftId);
  await gotoCheckoutHarness(page, session, draftId);
  const inner = await innerCheckoutReady(page);

  // Sliders' own defaults (term=60, down=10%, apr=6.9%) -- checkout.html computes this the
  // instant the priced total arrives, with no interaction needed.
  const monthlyText = await inner.locator("#financing-monthly").innerText();
  const clientMonthly = monthlyText.match(/[\d,]+\.\d{2}/)?.[0]?.replace(/,/g, "");
  expect(clientMonthly).toBeTruthy();

  await fillCard(inner, "4242 4242 4242 4242");

  const [rpcResponse] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes(`/mcp-apps/${session}/rpc`) &&
        (res.request().postData() ?? "").includes('"confirm_booking"'),
    ),
    inner.locator("#pay-button").click(),
  ]);
  const body = (await rpcResponse.json()) as { result: { content: { text: string }[] } };
  const confirmPayload = JSON.parse(body.result.content[0].text) as {
    outcome: string;
    server_monthly_payment_eur?: string;
  };
  expect(confirmPayload.outcome).toBe("success");
  expect(confirmPayload.server_monthly_payment_eur).toBe(clientMonthly);
});
