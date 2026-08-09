import { expect, test } from "@playwright/test";

/**
 * Gate 13.5 -- PLAN-02 P13.
 *
 * Drives `harness.html`, the same fixture harness gate 6.2 uses: real compiler output from
 * `src/mcp/ui/compiler.py`, rendered through the real `MessageProcessor` and the real
 * `carCatalog`. That matters more than it sounds -- a hand-written fixture would prove the
 * React component renders, but not that the *server-side* catalog spec and the *client-side*
 * zod schema agree about what a `CarCard` prop is called. A prop registered on one side only
 * is exactly the failure this asserts against (CONSTITUTION II.4).
 */

test("dealer attribution renders on a real CarCard", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });

  await page.goto("/harness.html?fixture=results.json");

  const dealers = page.getByTestId("car-card-dealer");
  await expect(dealers.first()).toBeVisible();
  expect(await dealers.count()).toBeGreaterThanOrEqual(2);

  const first = dealers.first();
  // A name, a city and a rating -- proposal doc #4's "a dealer a buyer can picture".
  await expect(first.locator(".cardinal-dealer-name")).not.toBeEmpty();
  await expect(first.locator(".cardinal-dealer-city")).not.toBeEmpty();
  // A rating like "4.3" plus a star glyph -- matched by shape, not by the literal
  // character, so the assertion survives an encoding round-trip.
  await expect(first.locator(".cardinal-dealer-rating")).toHaveText(/^\d\.\d\S$/);

  // Zero console errors: a prop the client schema rejects surfaces here, not as a silent
  // missing element.
  expect(errors).toEqual([]);
});

test("verification state is always stated, never left blank", async ({ page }) => {
  await page.goto("/harness.html?fixture=results.json");

  const badges = page.locator(".cardinal-dealer-verified");
  const count = await badges.count();
  expect(count).toBeGreaterThanOrEqual(2);

  for (let i = 0; i < count; i += 1) {
    const badge = badges.nth(i);
    await expect(badge).toBeVisible();
    // Whichever way it went, it says something. Silence about who you are paying is the
    // thing P14's payee disclosure exists to prevent.
    await expect(badge).toHaveText(/Verified dealer|Unverified/);
  }

  // The fixture deliberately includes one unverified dealer, so the cautious branch is
  // exercised in a golden fixture rather than only in theory.
  await expect(page.locator('.cardinal-dealer-verified[data-verified="no"]').first()).toBeVisible();
});

test("condition renders as a human label, not an enum value", async ({ page }) => {
  await page.goto("/harness.html?fixture=results.json");

  const condition = page.locator(".cardinal-condition").first();
  await expect(condition).toBeVisible();
  await expect(condition).toHaveText(/New|Used|Certified pre-owned/);
  // `certified_pre_owned` reaching a buyer's screen is the tell that a value went out
  // unmapped.
  await expect(condition).not.toHaveText(/certified_pre_owned/);
});

