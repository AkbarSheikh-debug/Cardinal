import { defineConfig } from "@playwright/test";

// Gate 8 (PHASE-8-COMMERCE.md): a separate config from playwright.config.ts (gate 6.2) and
// playwright.mcp-apps.config.ts (gate 7), same reasoning D-033/gate 7's own comment already
// gives -- each gate's browser run should never pay for, or depend on, a backend a different
// gate started. `scripts/gate_phase8.py` starts its own backend (on its own port, distinct
// from gate 7's) before Playwright launches; this config only brings up the built frontend.
export default defineConfig({
  testDir: "./tests",
  testMatch: "commerce.spec.ts",
  fullyParallel: false, // one shared backend process + in-memory booking store; concurrent runs would race it
  reporter: [["json", { outputFile: "test-results/commerce.json" }], ["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: {
    // Same port and build as gate 6/7's own configs -- one built frontend (vite.config.ts's
    // multi-entry build already includes mcp-host-harness.html unconditionally), reused
    // across gates rather than a third copy on a third port.
    command: "npm run build && npm run preview",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
