/**
 * Gate 6.2: every golden-message fixture (`web/public/fixtures/*.json`, exported straight
 * from `src/mcp/ui/compiler.py` by `scripts/export_ui_fixtures.py`) renders through the real
 * `harness.html` page -- real `MessageProcessor`, real `carCatalog`, real `A2uiSurface` --
 * with zero console errors or warnings.
 */
import { expect, test } from "@playwright/test";

const FIXTURES = [
  "progress.json",
  "results.json",
  "detail.json",
  "tco.json",
  "tco_breakdown.json",
  "score_breakdown.json",
];

for (const fixture of FIXTURES) {
  test(`${fixture} renders with zero console errors or warnings`, async ({ page }) => {
    const messages: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error" || msg.type() === "warning") {
        messages.push(`[${msg.type()}] ${msg.text()}`);
      }
    });
    page.on("pageerror", (err) => messages.push(`[pageerror] ${err.message}`));

    await page.goto(`/harness.html?fixture=${fixture}`);
    await page.waitForSelector('[data-testid="harness-root"][data-loaded="true"]');
    // The A2uiSurface must actually have mounted something, not just resolved the fetch.
    await expect(page.locator(".cardinal-surface")).toHaveCount(1);

    expect(messages, `console output for ${fixture}:\n${messages.join("\n")}`).toEqual([]);
  });
}
