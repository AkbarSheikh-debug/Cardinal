import { expect, type Page } from "@playwright/test";

/**
 * Sign a buyer in, because the agent lives at `/chat` and `/chat` is guarded (D-085). `/` is
 * now the public showroom, so the sign-in screen is no longer the *first* thing a visitor
 * sees -- but it is still the first thing a spec driving the agent has to do.
 *
 * Every caller gets a **unique email by default**. Accounts persist in Postgres and the
 * profile is written once at signup, so a shared address would carry whichever profile the
 * first run happened to create -- and a spec that passes only on a fresh database is a spec
 * that fails on the second run for a reason nobody can see.
 *
 * `expectUrl` overrides the landing assertion for the one case that legitimately lands
 * elsewhere: a visitor bounced here from a guarded route is returned to *that* route, not to
 * `/chat`.
 */
export async function signInAsBuyer(
  page: Page,
  options: { email?: string; session?: string; expectUrl?: RegExp } = {},
): Promise<string> {
  const email = options.email ?? `e2e-buyer+${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;

  // Only navigate if we are not already here. A caller that arrived by being *bounced* here
  // from a guarded route carries the attempted path in the router's history state, and a fresh
  // `goto` would throw that away -- which is exactly the thing the "returns you to where you
  // were headed" spec is trying to observe.
  if (!new URL(page.url(), "http://localhost").pathname.endsWith("/login")) {
    await page.goto("/login");
  }
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code" }).click();

  await page.getByLabel("Code").fill("123456");
  await page.getByLabel("Full name").fill("E2E Buyer");
  await page.getByLabel("Phone").fill("+49 170 1234567");
  await page.getByLabel("City").fill("Berlin");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(options.expectUrl ?? /\/chat$/);

  // A spec that needs a *specific* chat session id navigates again now that the cookie is
  // set; `?session=` is how the demo and cart specs pin one.
  if (options.session) {
    await page.goto(`/chat?session=${encodeURIComponent(options.session)}`);
    await expect(page.getByTestId("chat-input")).toBeVisible();
  }
  return email;
}
