import { defineConfig } from "@playwright/test";

// Gate 12 (PLAN-02 P12, criterion 12.2): its own config, same reason gates 6/7/8/11 keep
// theirs separate -- each run pays for exactly the backend it needs and no run's testMatch
// accidentally picks up another gate's spec.
//
// `scripts/gate_phase12.py` starts and tears down the API itself on a dedicated port and
// points the built frontend at it via `CARDINAL_API_PORT`, exactly as gates 7/8/11 do.
export default defineConfig({
  testDir: "./tests",
  testMatch: "auth.spec.ts",
  fullyParallel: false,
  reporter: [["json", { outputFile: "test-results/auth.json" }], ["list"]],
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
