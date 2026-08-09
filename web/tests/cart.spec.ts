/**
 * Gate 14 -- PLAN-02 P14. The browser half.
 *
 * 14.1/14.2/14.3/14.4/14.5/14.7/14.10/14.12 -- every criterion that needs to observe what
 * actually renders, or a real click event. The rest (14.6/14.8/14.9/14.11) are pure Python and
 * run directly in `scripts/gate_phase14.py`, the split D-015 established.
 *
 * Runs against a real backend with the environment scrubbed to `DEMO_MODE=true`
 * (`scripts/gate_phase14.py` starts it on its own port, the pattern gates 7/8/11/12 use), so
 * this is also gate 14.12's own evidence: a keyless machine walking add-to-cart -> `/cart` ->
 * mock pay.
 *
 * `test.describe.configure({ mode: "serial" })` plus one shared page is deliberate. The chain
 * *is* the thing under test -- a cart survives a navigation, a checkout follows an add -- and
 * re-running the whole flow per criterion would both triple the runtime and stop asserting
 * that the steps connect.
 */
import { test, expect, type Frame, type Page } from "@playwright/test";

// No `@types/node` dependency in this project (commerce.spec.ts's own note).
declare const process: { env: Record<string, string | undefined> };

/** A listing whose dealer is verified, and one whose dealer is not -- picked from the real
 * generated catalogue by `scripts/gate_phase14.py` so both branches of the payee disclosure
 * are exercised against real data rather than a hand-written pair. */
const VERIFIED = {
  source: process.env.CARDINAL_TEST_VERIFIED_SOURCE ?? "",
  sourceId: process.env.CARDINAL_TEST_VERIFIED_SOURCE_ID ?? "",
};
const UNVERIFIED = {
  source: process.env.CARDINAL_TEST_UNVERIFIED_SOURCE ?? "",
  sourceId: process.env.CARDINAL_TEST_UNVERIFIED_SOURCE_ID ?? "",
};

const VIEWPORT = { width: 1280, height: 900 };

const BUYER_EMAIL = "gate14-buyer@example.com";

/**
 * Three agent sessions, deliberately, because the scripted `DEMO_MODE` run is not passive: it
 * walks all the way to opening the *booking form* App on its own (gate 11's beat 6). Sharing
 * one session between "watch the agent work" and "drive the cart's own checkout" would have
 * the two racing to mount an App over each other, and the failure would look like a cart bug.
 *
 * - `CHAT_SESSION`  -- the agent runs; 14.7 and 14.1 use its rendered result cards.
 * - `RAIL_SESSION`  -- the agent runs *while the buyer sits on `/cart`* (14.3).
 * - `CHECKOUT_SESSION` -- no scripted run at all, so the only thing that mounts an App is the
 *   cart's own "Proceed to checkout" click (14.2/14.4/14.12).
 */
const CHAT_SESSION = `gate14-chat-${Date.now()}`;
const RAIL_SESSION = `gate14-rail-${Date.now()}`;
const CHECKOUT_SESSION = `gate14-checkout-${Date.now()}`;

test.use({ viewport: VIEWPORT });
test.describe.configure({ mode: "serial" });

let page: Page;

async function waitForBlobFrameWithSelector(target: Page, selector: string): Promise<Frame> {
  const start = Date.now();
  while (Date.now() - start < 20_000) {
    for (const frame of target.frames()) {
      if (!/^blob:/.test(frame.url())) continue;
      if (await frame.locator(selector).count().catch(() => 0)) return frame;
    }
    await target.waitForTimeout(150);
  }
  throw new Error(`no blob frame with ${selector} within 20s`);
}

async function cartCount(target: Page): Promise<number> {
  const response = await target.request.get("/cart/count");
  expect(response.ok()).toBe(true);
  return (await response.json()).count as number;
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: VIEWPORT });

  await page.goto("/login");
  await page.getByLabel("Email").fill(BUYER_EMAIL);
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("Code").fill("123456");
  await page.getByLabel("Full name").fill("Gate 14 Buyer");
  await page.getByLabel("Phone").fill("+49 170 1234567");
  await page.getByLabel("City").fill("Berlin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/chat$/);
});

test.afterAll(async () => {
  await page?.close();
});

// -- 14.7 -----------------------------------------------------------------------------------

test("14.7 nothing reaches the cart or checkout without a real click", async () => {
  await page.goto(`/chat?session=${encodeURIComponent(CHAT_SESSION)}`);
  await expect(page.getByTestId("cart-badge")).toBeVisible();
  await expect(page.getByTestId("cart-badge-count")).toHaveText("0");

  // A full scripted agent run: interview, research, ranking, results cards, all of it.
  const started = await page.request.post(`/demo/${CHAT_SESSION}/start`);
  expect(started.ok()).toBe(true);

  const cards = page.locator(".cardinal-car-card");
  await expect(cards.first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".cardinal-add-to-cart").first()).toBeVisible();

  // Let the scripted run reach its own end -- it opens the *booking form* App by itself,
  // which is correct and always was: `open_booking_form` is a form, model-visible by design.
  const host = page.getByTestId("mcp-app-host");
  await expect(host).toBeVisible({ timeout: 25_000 });

  // What the agent may never do on its own is open *checkout*. It didn't.
  await expect(host).toHaveAttribute("data-resource-uri", "ui://booking/form");

  // Nor add anything to the cart. It had a surface full of add controls in front of it and
  // every opportunity to use one: it cannot, because the cart is mutated by an authenticated
  // call carrying the buyer's httpOnly cookie -- a credential that lives in this browser and
  // not in the agent process. There is no cart tool to guard because there is no cart tool.
  expect(await cartCount(page)).toBe(0);
  await expect(page.getByTestId("cart-badge-count")).toHaveText("0");

  // Close the App so the cards underneath are clickable for 14.1.
  await host.getByRole("button", { name: "Close" }).click();
  await expect(host).toHaveCount(0);
});

// -- 14.1 -----------------------------------------------------------------------------------

test("14.1 add-to-cart from a real CarCard click reaches the cart and updates the badge", async () => {
  const button = page.locator(".cardinal-add-to-cart").first();
  await expect(button).toBeVisible();

  // A real, `isTrusted` click on the rendered card -- not a fetch this test performed.
  await button.click();

  // No reload, no navigation: the badge in the header reflects it in place.
  await expect(page.getByTestId("cart-badge-count")).toHaveText("1", { timeout: 10_000 });
  expect(page.url()).toContain(`/chat?session=${encodeURIComponent(CHAT_SESSION)}`);

  // And it is genuinely in the server's cart, not only in the badge's head.
  expect(await cartCount(page)).toBe(1);

  // Idempotent: the same car clicked twice is one line, not a quantity of two.
  await button.click();
  await page.waitForTimeout(500);
  expect(await cartCount(page)).toBe(1);
});

// -- 14.5 -----------------------------------------------------------------------------------

test("14.5 an unverified payee renders the explicit unverified state; a verified one does not", async () => {
  expect(VERIFIED.sourceId, "gate_phase14.py must pass a verified-dealer listing").not.toBe("");
  expect(UNVERIFIED.sourceId, "gate_phase14.py must pass an unverified-dealer listing").not.toBe(
    "",
  );

  // Added through the API rather than by a click: this criterion is about *rendering* the two
  // branches, and 14.1 above already proved the click path. Both use the same browser context,
  // so both carry the same buyer's cookie.
  for (const listing of [VERIFIED, UNVERIFIED]) {
    const response = await page.request.post("/cart/items", {
      data: { source: listing.source, source_id: listing.sourceId, offer_type: "buy" },
    });
    expect(response.ok(), `adding ${listing.source}:${listing.sourceId} failed`).toBe(true);
  }

  await page.goto(`/cart?session=${encodeURIComponent(CHAT_SESSION)}`);
  await expect(page.getByTestId("cart-panel")).toBeVisible();

  const flagged = page.locator('[data-testid="cart-payee"][data-flag="yes"]');
  const clean = page.locator('[data-testid="cart-payee"][data-flag="no"]');
  await expect(flagged.first()).toBeVisible();
  await expect(clean.first()).toBeVisible();

  // The unverified one says so, in as many words.
  await expect(flagged.first().getByTestId("cart-payee-status")).toContainText(
    "PAYEE IDENTITY UNVERIFIED",
  );
  // The verified one does not -- a flag that fires on everything is not a flag.
  await expect(clean.first().getByTestId("cart-payee-status")).not.toContainText("UNVERIFIED");
});

// -- 14.3 -----------------------------------------------------------------------------------

test("14.3 the chat rail is mounted and live on /cart", async () => {
  // A fresh agent session, entered *from the cart page* -- so everything below happens with
  // the buyer looking at their order, never having navigated away.
  await page.goto(`/cart?session=${encodeURIComponent(RAIL_SESSION)}`);
  await expect(page.getByTestId("cart-panel")).toBeVisible();

  const input = page.getByTestId("chat-input");
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();

  // The composer on this page posts to *this* session -- the same one an App mounted from
  // this page would arrive on. Asserted on the request the browser actually makes, because
  // that is the thing that could silently be wired to a different session.
  const sent = page.waitForRequest(
    (request) =>
      request.url().includes(`/sessions/${RAIL_SESSION}/messages`) && request.method() === "POST",
  );
  await input.fill("Is insurance included on that one?");
  await page.getByRole("button", { name: "Send" }).click();
  await sent;

  // And the agent's own turns render here, in the rail, while the cart is on screen.
  // `DEMO_MODE` answers a *typed* turn with a 403 by design -- the scripted run is the only
  // turn source on a machine with no API key (CONSTITUTION III.7) -- so the reply that has to
  // render is a real scripted one, pushed over this session's SSE stream. Identical
  // transport, identical rail, identical rendering path a live reply takes.
  const started = await page.request.post(`/demo/${RAIL_SESSION}/start`);
  expect(started.ok()).toBe(true);

  await expect(page.locator(".msg-assistant").first()).toBeVisible({ timeout: 20_000 });
  await expect(page).toHaveURL(/\/cart/);
  // The cart is still there beside it -- the conversation was never left.
  await expect(page.getByTestId("cart-panel")).toBeVisible();
});

// -- 14.2 -----------------------------------------------------------------------------------

test("14.2 /cart mounts the same ui://checkout/payment resource", async () => {
  // A session with no scripted run on it, so the only thing that can mount an App here is
  // the click below. Same cart -- it is the account's, not the session's.
  await page.goto(`/cart?session=${encodeURIComponent(CHECKOUT_SESSION)}`);
  await expect(page.getByTestId("cart-panel")).toBeVisible();
  await expect(page.getByTestId("mcp-app-host")).toHaveCount(0);

  const line = page.getByTestId("cart-line").first();
  await expect(line).toBeVisible();
  await line.getByTestId("cart-line-checkout").click();

  // Step one is the *booking form* App -- the mandatory form-fill App, not skipped.
  const host = page.getByTestId("mcp-app-host");
  await expect(host).toBeVisible({ timeout: 20_000 });
  await expect(host).toHaveAttribute("data-resource-uri", "ui://booking/form");

  const bookingFrame = await waitForBlobFrameWithSelector(page, "#form-root");
  await bookingFrame.locator("#form-root").waitFor({ state: "visible", timeout: 15_000 });
  await bookingFrame.locator("#name").fill("Gate 14 Buyer");
  await bookingFrame.locator("#email").fill(BUYER_EMAIL);
  await bookingFrame.locator("#collection_location").fill("Berlin");
  await bookingFrame.locator("#submit-button").click();
  await expect(bookingFrame.locator("#status")).toContainText("submitted", { timeout: 15_000 });

  // Step two: the checkout App. Asserted by resource URI read off the live host element --
  // the only place "the same resource the in-chat flow mounts" can actually be observed.
  await expect(host).toHaveAttribute("data-resource-uri", "ui://checkout/payment", {
    timeout: 20_000,
  });
  // Still on the cart page. Nothing navigated.
  await expect(page).toHaveURL(/\/cart/);
});

// -- 14.4 -----------------------------------------------------------------------------------

test("14.4 payee legal name, address and phone render above the fold and above the pay control", async () => {
  const checkoutFrame = await waitForBlobFrameWithSelector(page, "#pay-button");
  await checkoutFrame.locator("#form-root").waitFor({ state: "visible", timeout: 15_000 });

  const legal = checkoutFrame.getByTestId("payee-legal-name");
  const address = checkoutFrame.getByTestId("payee-address");
  const phone = checkoutFrame.getByTestId("payee-phone");
  await expect(legal).toBeVisible();
  await expect(legal).not.toBeEmpty();
  await expect(address).not.toBeEmpty();
  await expect(phone).not.toBeEmpty();

  // Geometric, not presence: a disclosure below the pay button, or below the fold, is a
  // disclosure nobody reads -- the same standard gate 8.10 holds the MOCK banner to.
  const payeeBox = await checkoutFrame.getByTestId("payee-block").boundingBox();
  const payBox = await checkoutFrame.locator("#pay-button").boundingBox();
  expect(payeeBox).not.toBeNull();
  expect(payBox).not.toBeNull();
  expect(payeeBox!.y + payeeBox!.height).toBeLessThanOrEqual(payBox!.y);
  expect(payeeBox!.y).toBeGreaterThanOrEqual(0);
  expect(payeeBox!.y + payeeBox!.height).toBeLessThanOrEqual(VIEWPORT.height);
});

// -- 14.12 ----------------------------------------------------------------------------------

test("14.12 DEMO_MODE walks add-to-cart -> /cart -> mock pay with the environment unset", async () => {
  const checkoutFrame = await waitForBlobFrameWithSelector(page, "#pay-button");

  // The on-screen mock banner was removed (D-091); the form itself is still exercised end to
  // end below, with a real click, the same `isTrusted` gesture gate 8.3 insists on. Everything
  // before it in this file was reached from a cart the buyer filled by clicking a card.
  await checkoutFrame.locator("#card_name").fill("Gate 14 Buyer");
  await checkoutFrame.locator("#card_number").fill("4242 4242 4242 4242");
  await checkoutFrame.locator("#card_expiry").fill("12/30");
  await checkoutFrame.locator("#card_cvc").fill("123");
  await checkoutFrame.locator("#pay-button").click();

  await expect(checkoutFrame.locator("#status")).toHaveAttribute("data-outcome", "success", {
    timeout: 20_000,
  });
  await expect(page).toHaveURL(/\/cart/);
});

// -- 14.10 ----------------------------------------------------------------------------------

test("14.10 a withdrawn cart line is refused with a distinct, non-spinner state", async ({
  browser,
}) => {
  // Its own page: this is the one case the running backend cannot produce on demand. A
  // listing can only be withdrawn *after* it was added (the API refuses to add an
  // unavailable one), and there is no route that withdraws one. So the *server* half is
  // asserted in Python -- `scripts/gate_phase14.py` withdraws a listing behind a cart it
  // already filled and checks the 409 and the `available: false` -- and this half asserts the
  // rendering of exactly that payload, fulfilled here by the browser rather than the app.
  const isolated = await browser.newPage({ viewport: VIEWPORT });
  try {
    await isolated.route("**/cart/items", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          checkout_is_single_item: true,
          items: [
            {
              item_id: "11111111-1111-1111-1111-111111111111",
              source: "mock_autobazaar",
              source_id: "AB-0001",
              offer_type: "buy",
              added_at: "2026-08-09T12:00:00+00:00",
              available: false,
              headline: "2021 Test Withdrawn Car",
              condition: "used",
              price: { amount: "20000", currency: "EUR" },
              payee: null,
            },
          ],
        }),
      });
    });

    await isolated.goto("/login");
    await isolated.getByLabel("Email").fill("gate14-withdrawn@example.com");
    await isolated.getByRole("button", { name: "Send code" }).click();
    await isolated.getByLabel("Code").fill("123456");
    await isolated.getByLabel("Full name").fill("Gate 14 Withdrawn");
    await isolated.getByLabel("Phone").fill("+49 170 1234567");
    await isolated.getByLabel("City").fill("Berlin");
    await isolated.getByRole("button", { name: "Sign in" }).click();

    await isolated.goto("/cart");
    const line = isolated.getByTestId("cart-line").first();
    await expect(line).toBeVisible();
    await expect(line).toHaveAttribute("data-available", "false");

    // A distinct state, in words, with an alert role -- not a spinner and not silence.
    const notice = line.getByTestId("cart-line-unavailable");
    await expect(notice).toBeVisible();
    await expect(notice).toContainText(/withdrawn/i);
    await expect(notice).toHaveAttribute("role", "alert");

    // And the pay path is closed rather than merely discouraged.
    await expect(line.getByTestId("cart-line-checkout")).toBeDisabled();

    // An unknown payee is stated, never omitted.
    await expect(line.getByTestId("cart-payee-status")).toContainText("PAYEE IDENTITY UNVERIFIED");
  } finally {
    await isolated.close();
  }
});
