import { defineConfig } from "@playwright/test";

// Gate 7 (PHASE-7-MCP-APPS.md): a separate config from playwright.config.ts (gate 6.2) so
// gate 6's A2UI-only run never pays for -- or depends on -- a Python backend it doesn't need.
//
// Only the frontend is a `webServer` entry here: the backend (`src.api.main:app`, which lazily
// spawns `booking-mcp`'s own HTTP transport on first use) is started and torn down by
// `scripts/gate_phase7.py` itself, using `sys.executable` so it runs inside this project's own
// virtualenv regardless of what a bare `python` on PATH resolves to -- a real risk on a machine
// where those differ, discovered while building this phase. Playwright's own `webServer.command`
// is a shell string with no clean way to reference that same interpreter portably.
export default defineConfig({
  testDir: "./tests",
  testMatch: "mcp-apps.spec.ts",
  fullyParallel: false, // one shared backend process + audit log; concurrent runs would race it
  reporter: [["json", { outputFile: "test-results/mcp-apps.json" }], ["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: {
    command: "npm run build && npm run preview",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
