/**
 * Gate 15 -- PLAN-02 P15. The browser half.
 *
 * 15.4 (a lead reaching an open SSE stream), 15.8 (tier phrasing on *rendered* text) and
 * 15.10 (`DEMO_MODE` end to end, no keys) need a real browser; the rest are pure Python in
 * `scripts/gate_phase15.py`, the split D-015 established.
 *
 * Two browser contexts, deliberately: a buyer and a seller signed in at the same time, which
 * is the only way to assert that an action in one produces a notification in the other. One
 * context with two cookie jars would not be the thing under test.
 */
import { test, expect, type Page } from "@playwright/test";

// No `@types/node` dependency in this project (commerce.spec.ts's own note).
declare const process: { env: Record<string, string | undefined> };

/** The dealership that owns the car the buyer will engage with -- resolved from the real
 * generated catalogue by `scripts/gate_phase15.py` and passed through, so this spec never
 * has to guess which seller should receive the lead. */
const DEALER_ID = process.env.CARDINAL_TEST_DEALER_ID ?? "";
const LISTING_SOURCE = process.env.CARDINAL_TEST_SOURCE ?? "";
const LISTING_SOURCE_ID = process.env.CARDINAL_TEST_SOURCE_ID ?? "";

const VIEWPORT = { width: 1280, height: 900 };
const BUYER_EMAIL = `gate15-buyer-${Date.now()}@example.com`;
const SELLER_EMAIL = `gate15-seller-${Date.now()}@example.com`;

test.use({ viewport: VIEWPORT });
test.describe.configure({ mode: "serial" });

let buyerPage: Page;
let sellerPage: Page;

async function signInBuyer(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(BUYER_EMAIL);
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("Code").fill("123456");
  await page.getByLabel("Full name").fill("Gate 15 Buyer");
  await page.getByLabel("Phone").fill("+49 170 1234567");
  await page.getByLabel("City").fill("Berlin");
  // Deliberately supplied: every privacy assertion below is only meaningful if this buyer
  // actually has an income on file that could leak to the seller.
  await page.getByLabel(/Annual income/).fill("88000");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/chat$/);
}

async function signInSeller(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByRole("button", { name: /selling/i }).click();
  await page.getByLabel("Email").fill(SELLER_EMAIL);
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("Code").fill("234567");
  await page.getByLabel("Full name").fill("Gate 15 Seller");
  await page.getByLabel("Phone").fill("+49 170 7654321");

  const picker = page.getByTestId("dealer-picker");
  await expect(picker).toBeVisible();
  // Populated from `GET /seller/dealers` -- a real fetch, so this also proves the picker is
  // not a hardcoded list that could drift from the directory leads are routed by.
  await expect(picker.locator("option")).not.toHaveCount(1);
  await picker.selectOption(DEALER_ID);

  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/seller$/);
}

test.beforeAll(async ({ browser }) => {
  // Separate contexts, not just separate pages: each needs its own cookie jar.
  buyerPage = await (await browser.newContext({ viewport: VIEWPORT })).newPage();
  sellerPage = await (await browser.newContext({ viewport: VIEWPORT })).newPage();
  await signInBuyer(buyerPage);
  await signInSeller(sellerPage);
});

test.afterAll(async () => {
  await buyerPage?.close();
  await sellerPage?.close();
});

// -- 15.6 -----------------------------------------------------------------------------------

test("15.6 a buyer who only browsed produces no lead and exposes no contact details", async () => {
  // The buyer is signed in and has loaded the app. That is browsing, and it must produce
  // nothing -- the console says so in words rather than rendering an empty list with no
  // explanation.
  await expect(sellerPage.getByTestId("seller-console")).toBeVisible();
  await expect(sellerPage.getByTestId("seller-empty")).toBeVisible();
  await expect(sellerPage.getByTestId("lead-card")).toHaveCount(0);

  const body = (await sellerPage.locator("body").innerText()).toLowerCase();
  expect(body).not.toContain(BUYER_EMAIL.toLowerCase());
  expect(body).not.toContain("gate 15 buyer");
});

// -- 15.4 -----------------------------------------------------------------------------------

test("15.4 a new lead reaches an open /seller/events stream without a reload", async () => {
  // The console is already open and its EventSource is connected -- asserted, not assumed.
  await expect(sellerPage.locator(".seller-sub")).toContainText("Live");

  // A real intent action in the *other* browser context.
  const added = await buyerPage.request.post("/cart/items", {
    data: { source: LISTING_SOURCE, source_id: LISTING_SOURCE_ID, offer_type: "buy" },
  });
  expect(added.ok(), await added.text()).toBe(true);

  // No reload, no navigation, no polling loop in the page: the card arrives because the
  // server pushed a nudge down the stream this console already had open.
  await expect(sellerPage.getByTestId("lead-card")).toHaveCount(1, { timeout: 15_000 });
  await expect(sellerPage.getByTestId("lead-buyer")).toHaveText("Gate 15 Buyer");
  expect(sellerPage.url()).toContain("/seller");
});

// -- 15.8 -----------------------------------------------------------------------------------

test("15.8 every tier renders as an estimate with its reasoning, never as an assertion", async () => {
  const card = sellerPage.getByTestId("lead-card").first();

  const tier = card.getByTestId("lead-tier");
  await expect(tier).toBeVisible();
  await expect(tier).toContainText("(estimated)");
  // The words a dashboard must never put on screen about a person.
  await expect(tier).not.toContainText(/will buy|definitely|guaranteed/i);

  // The reasoning is next to the verdict, not hidden behind the expander.
  const explanation = card.getByTestId("lead-explanation");
  await expect(explanation).toBeVisible();
  await expect(explanation).toContainText("(estimated)");
  await expect(explanation).toContainText("added this car to their cart");

  // And every named signal is there, with its own sentence and its contribution.
  await card.getByTestId("lead-why-toggle").click();
  const why = card.getByTestId("lead-why");
  await expect(why).toBeVisible();
  const signals = why.getByTestId("lead-signal");
  expect(await signals.count()).toBe(7);
  for (let i = 0; i < 7; i += 1) {
    await expect(signals.nth(i).locator(".signal-why")).not.toBeEmpty();
    await expect(signals.nth(i).locator(".signal-contribution")).toHaveText(/^\+\d\.\d{3}$/);
  }
  // Stated on screen: the rows *are* the score, nothing is withheld.
  await expect(card.getByTestId("lead-signal-total")).toContainText("the whole score");
});

// -- 15.7 (rendered half) --------------------------------------------------------------------

test("15.7 no income-shaped value appears anywhere on the seller's screen", async () => {
  const body = (await sellerPage.locator("body").innerText()).toLowerCase();
  // The field names, the exact figure, and every band *value* -- stronger than the bare
  // word "band", which a dealership name could contain for reasons nothing to do with this.
  for (const term of [
    "income",
    "88000",
    "88,000",
    "salary",
    "undisclosed",
    "under_25k",
    "25k_50k",
    "50k_100k",
    "100k_plus",
  ]) {
    expect(body, `"${term}" reached the seller's screen`).not.toContain(term);
  }
});

// -- 15.10 ----------------------------------------------------------------------------------

test("15.10 DEMO_MODE drives a buyer action to a live seller dashboard with no keys", async () => {
  // The stronger signal: opening checkout. Same lead, re-scored, still one card.
  const cart = await buyerPage.request.get("/cart/items");
  const itemId = (await cart.json()).items[0].item_id;
  const opened = await buyerPage.request.post("/cart/checkout", {
    data: { session_id: `gate15-${Date.now()}`, item_id: itemId },
  });
  expect(opened.ok(), await opened.text()).toBe(true);

  const card = sellerPage.getByTestId("lead-card").first();
  await expect(card.getByTestId("lead-explanation")).toContainText("opened checkout", {
    timeout: 15_000,
  });
  await expect(sellerPage.getByTestId("lead-card")).toHaveCount(1);

  // The dealership this seller claimed at signup, and the analytics strip the console leads
  // with -- both real, both rendered.
  await expect(sellerPage.getByTestId("seller-dealer")).not.toBeEmpty();
  await expect(sellerPage.getByTestId("analytics-total")).toContainText("1");

  // The SLA countdown and the contact details a salesperson would act on.
  await expect(card.getByTestId("lead-sla")).not.toBeEmpty();
  await expect(card.getByTestId("lead-contact")).toContainText(BUYER_EMAIL);

  // And the one action the console offers.
  await card.getByTestId("lead-mark-contacted").click();
  await expect(card.getByTestId("lead-state")).toHaveText("contacted");
});
