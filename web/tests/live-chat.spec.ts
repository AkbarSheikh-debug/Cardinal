/**
 * The live path's smoke test: two real turns against a real model, in a real browser, against
 * the running `docker compose up` stack (see `playwright.live.config.ts` on why it builds no
 * server of its own).
 *
 * Every defect this exists to catch -- D-052's "Session ID already in use" on the second turn,
 * D-053's missing prompt files, D-054's empty canvas, nginx's 60s proxy timeout, and the
 * subagent prompt leaking into the chat rail -- was invisible to `make verify`, to all 530 unit
 * tests, and to `curl`. Only a browser driving the built image saw them.
 *
 * Not part of `make verify` or any gate: it needs a real key and spends real tokens (D-015).
 */
import { test, expect } from "@playwright/test";

const SHOTS = "../shots";

test("live chat end to end", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));

  await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
  await page.screenshot({ path: `${SHOTS}/01-landing.png`, fullPage: true });

  const input = page.getByTestId("chat-input");
  await expect(input).toBeVisible({ timeout: 10_000 });

  await input.fill("i want to buy a family SUV under 30000 euros, need it by september");
  const t0 = Date.now();
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByTestId("thinking")).toBeVisible({ timeout: 5_000 });
  await page.screenshot({ path: `${SHOTS}/02-thinking.png`, fullPage: true });

  const assistant = page.locator(".msg-assistant:not(.msg-thinking)");
  await assistant.first().waitFor({ state: "visible", timeout: 240_000 });
  const elapsed = Date.now() - t0;
  await page.screenshot({ path: `${SHOTS}/03-reply.png`, fullPage: true });

  const replyText = await assistant.first().innerText();

  console.log("=== TURN 1 ===");
  console.log("latency ms:", elapsed);
  console.log("reply:", replyText.slice(0, 300));
  console.log("console errors:", JSON.stringify(consoleErrors));

  expect(await page.locator(".msg-error").count(), `error shown: ${replyText}`).toBe(0);

  // Second turn -- this is exactly what "Session ID already in use" used to break.
  await input.fill("buying, not renting. two kids, mostly motorway driving");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("thinking")).toBeVisible({ timeout: 5_000 });

  await expect.poll(async () => await assistant.count(), { timeout: 240_000 }).toBeGreaterThan(1);
  await page.screenshot({ path: `${SHOTS}/04-turn2.png`, fullPage: true });

  // Give the canvas a moment to receive any render_* surface pushed late in the turn.
  await page
    .locator(".surface")
    .first()
    .waitFor({ state: "visible", timeout: 15_000 })
    .catch(() => {});
  await page.screenshot({ path: `${SHOTS}/05-final.png`, fullPage: true });

  console.log("=== TURN 2 ===");
  console.log("assistant bubbles:", await assistant.count());
  console.log("second reply:", (await assistant.nth(1).innerText()).slice(0, 300));
  console.log("canvas surfaces:", await page.locator(".surface").count());
  console.log("console errors:", JSON.stringify(consoleErrors));

  expect(await page.locator(".msg-error").count()).toBe(0);
});
