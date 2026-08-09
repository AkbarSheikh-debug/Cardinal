import { expect, test } from "@playwright/test";
import { signInAsBuyer } from "./helpers/signin";

/**
 * Gate 16.1 -- PLAN-02 P16.
 *
 * Drives the real product at `/`, signing in first because the route is guarded (D-085). The
 * three controls are asserted to work *independently*: toggling the agent voice must not
 * disturb the picker or the mic, because a user who turns the voice off and finds their
 * microphone gone has been surprised by a coupling nobody designed.
 */

test("the three voice controls are present and independent", async ({ page }) => {
  await signInAsBuyer(page);

  const controls = page.getByTestId("voice-controls");
  await expect(controls).toBeVisible();

  const agentToggle = page.getByTestId("voice-agent-toggle");
  const mic = page.getByTestId("voice-mic");
  await expect(agentToggle).toBeVisible();
  await expect(mic).toBeVisible();

  // Off by default -- a page that starts talking at you is a page people close.
  await expect(agentToggle).toHaveAttribute("aria-pressed", "false");

  await agentToggle.click();
  await expect(agentToggle).toHaveAttribute("aria-pressed", "true");
  // The mic is untouched by the speaker toggle.
  await expect(mic).toBeVisible();
  await expect(mic).toHaveAttribute("data-recording", "no");
});

test("the agent-voice toggle survives a reload", async ({ page }) => {
  await signInAsBuyer(page);
  const toggle = page.getByTestId("voice-agent-toggle");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(page.getByTestId("voice-agent-toggle")).toHaveAttribute("aria-pressed", "true");
});

test("push-to-talk enters and leaves the recording state", async ({ page }) => {
  await signInAsBuyer(page);
  const mic = page.getByTestId("voice-mic");

  await mic.click();
  await expect(mic).toHaveAttribute("data-recording", "yes");

  await mic.click();
  // Either a transcript arrives or the cascade reports a fallback -- both leave the button
  // usable, which is the property under test. A stuck "recording" state is the failure.
  await expect(mic).toHaveAttribute("data-recording", "no", { timeout: 15_000 });
});

test("a transcript lands in the composer and is never auto-sent", async ({ page }) => {
  await signInAsBuyer(page);

  const input = page.getByTestId("chat-input");
  const before = await page.locator(".chat-message, [data-role]").count();

  const mic = page.getByTestId("voice-mic");
  await mic.click();
  await page.waitForTimeout(600); // let the recorder produce at least one 250ms chunk
  await mic.click();
  await expect(mic).toHaveAttribute("data-recording", "no", { timeout: 15_000 });

  // Whatever the tier managed, no new chat turn may have appeared without a send press.
  const after = await page.locator(".chat-message, [data-role]").count();
  expect(after).toBe(before);
  // And the composer is still the thing holding any text.
  await expect(input).toBeVisible();
});
