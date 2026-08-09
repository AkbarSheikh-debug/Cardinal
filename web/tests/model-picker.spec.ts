/**
 * The INTERVIEW-only alternate-provider path (D-056), in a real browser against the running
 * docker stack. Uses Groq's free tier, not Claude, on purpose.
 *
 * Since D-059 the picker is a developer affordance rather than a product surface: `GET /models`
 * serves an empty list unless `CARDINAL_SHOW_MODEL_PICKER` is on, so the default demo shows no
 * model names at all and the interview runs on `CARDINAL_INTERVIEW_MODEL` (Qwen 3.6 by default).
 * The first test is the shipping configuration; the second only runs when the flag is set.
 */
import { test, expect, type Page } from "@playwright/test";
import { signInAsBuyer } from "./helpers/signin";

const SHOTS = "../shots";

/**
 * Whether this deployment has `CARDINAL_SHOW_MODEL_PICKER` on, asked of the running backend
 * rather than read from `process.env` -- the picker follows what `GET /models` actually serves,
 * and the backend under test is not necessarily the process running these tests.
 */
async function pickerEnabled(page: Page): Promise<boolean> {
  const response = await page.request.get("http://localhost:8000/models");
  if (!response.ok()) return false;
  return ((await response.json()) as unknown[]).length > 0;
}

test("no model is named in the UI, and the interview runs on the default", async ({ page }) => {
  test.skip(await pickerEnabled(page), "CARDINAL_SHOW_MODEL_PICKER is on -- picker expected");

  const consoleErrors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));

  await signInAsBuyer(page);
  await page.waitForLoadState("networkidle");

  const input = page.getByTestId("chat-input");
  await expect(input).toBeEnabled({ timeout: 10_000 });
  await expect(page.getByTestId("model-picker")).toHaveCount(0);

  // The point of hiding the picker is that no provider or model name reaches the page.
  const body = (await page.locator("body").innerText()).toLowerCase();
  for (const leak of ["qwen", "groq", "llama", "gpt-oss", "openrouter", "gemini", "nemotron"]) {
    expect(body, `"${leak}" is visible in the UI`).not.toContain(leak);
  }
  await page.screenshot({ path: `${SHOTS}/model-01-no-picker.png`, fullPage: true });

  await input.fill("I need a family SUV under 30000 euros");
  await page.getByRole("button", { name: "Send" }).click();

  const assistant = page.locator(".msg-assistant:not(.msg-thinking)");
  await assistant.first().waitFor({ state: "visible", timeout: 30_000 });

  // The relative-date turn is the one that used to fall through to "Sorry, could you say that
  // again?" -- the model had no current date to resolve "in 2 days" against and burned its
  // whole token budget deliberating inside <think> (D-058).
  await input.fill("rent it and i need it in 2 days");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(assistant.nth(1)).toBeVisible({ timeout: 30_000 });

  const replyText = await assistant.nth(1).innerText();
  await page.screenshot({ path: `${SHOTS}/model-02-relative-date.png`, fullPage: true });

  expect(await page.locator(".msg-error").count(), `error shown: ${replyText}`).toBe(0);
  expect(replyText).not.toContain("Sorry, could you say that again?");
  expect(replyText.length).toBeGreaterThan(0);
  expect(consoleErrors, JSON.stringify(consoleErrors)).toHaveLength(0);
});

test("picker selects Groq and runs the interview on it when enabled", async ({ page }) => {
  test.skip(!(await pickerEnabled(page)), "picker is hidden by default (D-059)");

  await signInAsBuyer(page);
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("model-picker")).toBeVisible({ timeout: 10_000 });

  const groqOption = page.getByTestId("model-option-groq/llama-3.3-70b-versatile");
  await groqOption.click();
  await expect(groqOption).toHaveClass(/selected/);

  const input = page.getByTestId("chat-input");
  await expect(input).toBeEnabled({ timeout: 10_000 });
  await input.fill("i need a cheap hatchback under 15000 euros, need it by 2026-11-01");
  await page.getByRole("button", { name: "Send" }).click();

  const assistant = page.locator(".msg-assistant:not(.msg-thinking)");
  await assistant.first().waitFor({ state: "visible", timeout: 30_000 });
  const replyText = await assistant.first().innerText();

  expect(await page.locator(".msg-error").count(), `error shown: ${replyText}`).toBe(0);
  expect(replyText.length).toBeGreaterThan(0);
});
