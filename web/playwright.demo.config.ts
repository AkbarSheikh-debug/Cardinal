import { defineConfig } from "@playwright/test";

// Gate 11 (PHASE-11-DELIVERY.md, criteria 11.3/11.4): its own config, same reason gate 7/8 keep
// theirs separate from playwright.config.ts (gate 6.2) -- each pays for exactly the backend it
// needs and no run's testMatch accidentally picks up another gate's spec.
//
// Only the frontend is a `webServer` entry here: `scripts/gate_phase11.py` starts and tears
// down the backend itself, on a dedicated port, with an environment scrubbed to just
// `DEMO_MODE=true` (gate 11.4's own evidence) -- the same reasoning gate 7's config comment
// gives for why `webServer.command` (a shell string) can't be the thing that launches it.
export default defineConfig({
  testDir: "./tests",
  testMatch: "demo-e2e.spec.ts",
  fullyParallel: false,
  reporter: [["json", { outputFile: "test-results/demo-e2e.json" }], ["list"]],
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
