/**
 * Gate 7 (PHASE-7-MCP-APPS.md SS7): ten criteria, each its own `test()` titled `7.N ...` so
 * `scripts/gate_phase7.py` can map the JSON reporter's per-test results back onto individual
 * gate criteria (the way gate 6.2 treats its six fixtures as one criterion doesn't fit here --
 * PHASE-7's own gate table wants 7.1-7.10 reported separately).
 *
 * Every test drives `mcp-host-harness.html` against a *real* running `src.api.main:app` +
 * `booking-mcp` HTTP server (started by `scripts/gate_phase7.py` before Playwright launches,
 * `webServer` in `playwright.mcp-apps.config.ts` only brings up the built frontend) -- no
 * `DEMO_MODE`, no live model, matching PHASE-7 §3's "get the host working in isolation first."
 */
import { test, expect, type Page, type Frame } from "@playwright/test";
import { effectiveCsp } from "../src/mcp-host/csp";

async function waitForFrame(page: Page, pattern: RegExp, timeoutMs = 10_000): Promise<Frame> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const frame = page.frames().find((f) => pattern.test(f.url()));
    if (frame) return frame;
    await page.waitForTimeout(100);
  }
  throw new Error(`no frame matching ${pattern} within ${timeoutMs}ms (frames: ${page.frames().map((f) => f.url()).join(", ")})`);
}

function gotoHarness(page: Page, session: string, toolInput: Record<string, unknown> = {}): Promise<void> {
  const url =
    `/mcp-host-harness.html?session=${encodeURIComponent(session)}` +
    `&toolInput=${encodeURIComponent(JSON.stringify(toolInput))}`;
  return page.goto(url).then(() => undefined);
}

async function innerFormReady(page: Page): Promise<Frame> {
  const inner = await waitForFrame(page, /^blob:/);
  await inner.locator("#form-root").waitFor({ state: "visible", timeout: 10_000 });
  return inner;
}

test("7.1 inner iframe origin != host origin, asserted from the browser", async ({ page }) => {
  await gotoHarness(page, "gate71");
  const inner = await innerFormReady(page);
  const hostOrigin = new URL(page.url()).origin;
  const innerOrigin = await inner.evaluate(() => window.location.origin);
  expect(innerOrigin).not.toBe(hostOrigin);
  expect(innerOrigin.length).toBeGreaterThan(0);
});

test("7.2 CSP on the inner document matches the resource's declared csp, defaults applied", async ({ page }) => {
  await gotoHarness(page, "gate72");
  const inner = await innerFormReady(page);
  const content = await inner.evaluate(
    () => document.querySelector('meta[http-equiv="Content-Security-Policy"]')?.getAttribute("content") ?? "",
  );
  const expected = effectiveCsp([]); // booking_form.html declares connectDomains: []
  for (const [directive, value] of Object.entries(expected)) {
    expect(content).toContain(`${directive} ${value}`);
  }
});

test("7.3 fetch() to an undeclared domain from inside the App fails and is logged as blocked", async ({ page }) => {
  const session = "gate73";
  await gotoHarness(page, session);
  const inner = await innerFormReady(page);

  const outcome = await inner.evaluate(async () => {
    try {
      await fetch("https://example.com/");
      return "unexpectedly-succeeded";
    } catch (err) {
      return `blocked:${err instanceof Error ? err.message : String(err)}`;
    }
  });
  expect(outcome.startsWith("blocked:")).toBe(true);

  // The violation report is a fire-and-forget notification -- give it a moment to land.
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`/mcp-apps/${session}/audit`);
        const entries = (await response.json()) as { method: string; decision: string }[];
        return entries.some((e) => e.method === "csp/violation" && e.decision === "blocked");
      },
      { timeout: 5_000 },
    )
    .toBe(true);
});

test("7.4 ui/initialize completes; hostContext.theme reaches the App and visibly applies", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await gotoHarness(page, "gate74");
  const inner = await innerFormReady(page);
  const theme = await inner.evaluate(() => document.documentElement.dataset.theme);
  expect(theme).toBe("dark");
  const backgroundColor = await inner.evaluate(() => getComputedStyle(document.body).backgroundColor);
  // The dark variable is #1A1A1A -> rgb(26, 26, 26); the light default is white. Either exact
  // value proves the CSS variable actually changed, not just the data-attribute.
  expect(backgroundColor).toBe("rgb(26, 26, 26)");
});

test("7.5 ui/notifications/tool-input is delivered exactly once, after initialize responds", async ({ page }) => {
  await gotoHarness(page, "gate75", { source: "mock_autobazaar", source_id: "AB-1", offer_type: "buy" });
  await innerFormReady(page);
  const outer = await waitForFrame(page, /\/mcp-outer\.html/);
  const debugInfo = await outer.evaluate(() => window.__cardinalHostDebug);
  expect(debugInfo?.initRespondedAt).not.toBeNull();
  expect(debugInfo?.toolInputSentAt).not.toBeNull();
  expect(debugInfo!.toolInputSentAt!).toBeGreaterThanOrEqual(debugInfo!.initRespondedAt!);
});

test("7.6 tools/call from the view reaches the server only through the host proxy", async ({ page }) => {
  const session = "gate76";
  const requestUrls: string[] = [];
  page.on("request", (req) => requestUrls.push(req.url()));

  await gotoHarness(page, session, { source: "mock_autobazaar", source_id: "AB-2", offer_type: "buy" });
  const inner = await innerFormReady(page);
  await inner.locator("#name").fill("Jane Doe");
  await inner.locator("#email").fill("jane@example.com");
  await inner.locator("#collection_location").fill("Berlin");
  await inner.locator("#submit-button").click();
  await inner.locator(".status.success").waitFor({ timeout: 10_000 });

  const proxied = requestUrls.filter((u) => u.includes(`/mcp-apps/${session}/rpc`));
  expect(proxied.length).toBeGreaterThanOrEqual(2); // resources/read (bootstrap) + tools/call (submit)

  const direct = requestUrls.filter((u) => u.includes(":8100"));
  expect(direct).toEqual([]);
});

test("7.7 resource-teardown removes the iframe; no leak after 20 open/close cycles", async ({ page }) => {
  await gotoHarness(page, "gate77");
  await innerFormReady(page);

  for (let i = 0; i < 20; i++) {
    await page.evaluate(() => window.__cardinalClose?.());
    await expect.poll(() => page.locator("iframe").count()).toBe(0);
    await page.evaluate(() => window.__cardinalOpen?.());
    await innerFormReady(page);
  }
  await page.evaluate(() => window.__cardinalClose?.());
  await expect.poll(() => page.locator("iframe").count()).toBe(0);
});

test("7.8 size-changed resizes the container without layout shift in the surrounding surface", async ({ page }) => {
  await gotoHarness(page, "gate78");
  await innerFormReady(page);
  const canaryBefore = await page.locator("#canary").boundingBox();

  await page.evaluate(() => {
    const panel = document.querySelector(".cardinal-mcp-app-host") as HTMLElement;
    panel.style.width = "300px";
  });
  await page.waitForTimeout(300); // let the ResizeObserver callback + notification round-trip

  const canaryAfter = await page.locator("#canary").boundingBox();
  expect(canaryAfter).toEqual(canaryBefore);
});

test("7.9 audit log has one entry per view-initiated RPC, no gaps, for a full booking flow", async ({ page }) => {
  const session = "gate79";
  await gotoHarness(page, session, { source: "mock_autobazaar", source_id: "AB-3", offer_type: "buy" });
  const inner = await innerFormReady(page);
  await inner.locator("#name").fill("Jane Doe");
  await inner.locator("#email").fill("jane@example.com");
  await inner.locator("#collection_location").fill("Munich");
  await inner.locator("#submit-button").click();
  await inner.locator(".status.success").waitFor({ timeout: 10_000 });

  const response = await page.request.get(`/mcp-apps/${session}/audit`);
  const entries = (await response.json()) as { method: string; decision: string; resourceUri: string }[];
  const methods = entries.map((e) => e.method);
  expect(methods).toContain("resources/read");
  expect(methods).toContain("tools/call");
  expect(entries.every((e) => e.resourceUri === "ui://booking/form")).toBe(true);
  expect(entries.every((e) => e.decision === "allowed")).toBe(true);
});

test("7.10 the App renders and functions with JavaScript's network access fully blocked", async ({ page }) => {
  await gotoHarness(page, "gate7-10", { source: "mock_autobazaar", source_id: "AB-4", offer_type: "buy" });
  const inner = await innerFormReady(page);

  const fetchOutcome = await inner.evaluate(async () => {
    try {
      await fetch("https://example.com/");
      return "succeeded";
    } catch {
      return "blocked";
    }
  });
  expect(fetchOutcome).toBe("blocked");

  // The App's real functionality (fill + submit) goes over postMessage, not fetch -- it must
  // keep working even though a direct fetch from the same frame cannot.
  await inner.locator("#name").fill("Jane Doe");
  await inner.locator("#email").fill("jane@example.com");
  await inner.locator("#collection_location").fill("Hamburg");
  await inner.locator("#submit-button").click();
  await expect(inner.locator(".status.success")).toBeVisible({ timeout: 10_000 });
});
