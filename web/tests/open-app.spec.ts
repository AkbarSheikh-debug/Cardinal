import { expect, test } from "@playwright/test";

/**
 * Not a gate -- a walkthrough of the *running* stack (`docker compose up`), so the finished
 * site can be looked at with human eyes. Screenshots land in `docs/screenshots/site-*.png`.
 *
 *   npx playwright test --config=playwright.open.config.ts
 */

const SHOTS = "../docs/screenshots";

// Viewport and colour scheme come from the config's two projects (dark 2000px, light 1440px).

// A unique address per run. The two theme projects share one backend, so a fixed email meant
// the second run reused the first's account -- and the resulting state difference made `light`
// fail only when it ran after `dark`. Same reasoning as the seller address below: a spec that
// depends on which run went first is a spec that fails for a reason nobody can see.
const BUYER = {
  name: "Demo Buyer",
  phone: "+49 170 1234567",
  city: "Berlin",
};
const buyerEmail = () => `demo.buyer+${Date.now()}@example.com`;

test("the whole site, end to end", async ({ page }) => {
  // 1 -- an anonymous visitor lands on the showroom: the front page is public
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("site-header")).toBeVisible();
  await expect(page.getByTestId("showroom")).toBeVisible();
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-site-0-showroom.png`, fullPage: true });

  // ...and the agent still asks who they are (D-085, one hop in)
  await page.goto("/chat");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("Email")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-site-1-login.png` });

  // 2 -- the seller side of the same screen
  await page.getByRole("button", { name: /selling/i }).click();
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-site-2-login-seller.png` });
  await page.getByRole("button", { name: /buying or renting/i }).click();

  // 3 -- buyer signup
  await page.getByLabel("Email").fill(buyerEmail());
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByLabel("Code")).toBeVisible();
  await page.getByLabel("Code").fill("123456");
  await page.getByLabel("Full name").fill(BUYER.name);
  await page.getByLabel("Phone").fill(BUYER.phone);
  await page.getByLabel("City").fill(BUYER.city);
  await page.getByLabel("I'm buying as").selectOption("corporate");
  await page.getByLabel(/Annual income/).fill("72000");
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-site-3-signup-form.png`, fullPage: true });
  await page.getByRole("button", { name: "Sign in" }).click();

  // 4 -- signed in: the header now carries the account, the cart and the voice controls
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByTestId("nav-account")).toContainText(BUYER.name);
  await expect(page.getByTestId("cart-badge")).toBeVisible();
  await expect(page.getByTestId("voice-controls")).toBeVisible();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-site-4-buyer-signed-in.png` });

  // The income rule, proven against the live stack rather than asserted in prose.
  const me = await (await page.request.get("/auth/me")).json();
  expect(me.profile.annual_income.amount).toBe("72000.00");
  expect(me.profile.income_band).toBe("50k_100k");
  console.log("AUTH/ME income:", me.profile.annual_income.amount, "->", me.profile.income_band);

  // 5 -- the cart, reached from the header
  await page.getByTestId("nav-cart").click();
  await expect(page).toHaveURL(/\/cart$/);
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-site-5-cart.png` });

  // 6 -- sign out, then in as a seller; the header follows the role
  await page.getByTestId("nav-signout").click();
  await expect(page.getByTestId("nav-signin")).toBeVisible();
  await page.goto("/login");
  await page.getByRole("button", { name: /selling/i }).click();
  // A fresh address per run: accounts persist in Postgres and the profile is written once at
  // signup, so reusing one would show whatever dealership it was created with (or none).
  await page.getByLabel("Email").fill(`demo.seller+${Date.now()}@example.com`);
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("Code").fill("234567");
  await page.getByLabel("Full name").fill("Demo Seller");
  await page.getByLabel("Phone").fill("+49 170 7654321");
  // P15 requires a seller to claim a dealership at signup (D-080) -- leads are routed by it.
  // Skipping this is what put "not linked to a dealership" on the console instead of a board.
  const dealerPicker = page.getByTestId("dealer-picker");
  await dealerPicker.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/seller$/);
  // A seller sees Leads and no cart -- links follow the role, not the route table.
  await expect(page.getByTestId("nav-seller")).toBeVisible();
  await expect(page.getByTestId("nav-cart")).toHaveCount(0);
  await expect(page.getByTestId("cart-badge")).toHaveCount(0);
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-site-6-seller-console.png`, fullPage: true });
});

test("the A2UI results cards with dealer attribution", async ({ page }) => {
  // `harness.html` ships in the built image, so this renders the real golden fixture through
  // the real catalog on the deployed stack.
  await page.goto("/harness.html?fixture=results.json");
  await expect(page.getByTestId("car-card-dealer").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-site-7-result-cards.png`, fullPage: true });
});
