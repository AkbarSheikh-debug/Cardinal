import { defineConfig } from "@playwright/test";

// Gate 15 (PLAN-02 P15): its own config, the same reason every other gate keeps one --
// each run pays for exactly the backend it needs and no run's `testMatch` picks up another
// gate's spec.
//
// `scripts/gate_phase15.py` starts and tears down the API itself on a dedicated port with
// the environment scrubbed to `DEMO_MODE=true`, and points the built frontend at it via
// `CARDINAL_API_PORT` -- exactly as gates 7/8/11/12/14 do.
export default defineConfig({
  testDir: "./tests",
  testMatch: "seller.spec.ts",
  // One backend, one in-memory lead store, and a serial chain where a buyer action in one
  // context has to show up in the other -- concurrent workers would race the same dealer's
  // inbox and the failure would look like a broken SSE stream.
  fullyParallel: false,
  workers: 1,
  reporter: [["json", { outputFile: "test-results/seller.json" }], ["list"]],
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
