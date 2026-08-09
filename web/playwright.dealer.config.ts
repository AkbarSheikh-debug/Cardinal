import { defineConfig } from "@playwright/test";

// Gate 13.5 (PLAN-02 P13). Reuses `harness.html` -- the same fixture harness gate 6.2 drives,
// which renders real compiler output through the real `MessageProcessor` and `carCatalog`.
// No backend: the fixture is exported ahead of the run by `scripts/gate_phase13.py`, so this
// asserts the *rendering* of dealer attribution rather than a live session's plumbing.
export default defineConfig({
  testDir: "./tests",
  testMatch: "dealer-card.spec.ts",
  fullyParallel: false,
  reporter: [["json", { outputFile: "test-results/dealer.json" }], ["list"]],
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
