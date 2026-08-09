import { defineConfig } from "@playwright/test";

// Gate 14 (PLAN-02 P14): its own config, the same reason gates 6/7/8/11/12 keep theirs
// separate -- each run pays for exactly the backend it needs, and no run's `testMatch`
// accidentally picks up another gate's spec.
//
// `scripts/gate_phase14.py` starts and tears down the API itself on a dedicated port with the
// environment scrubbed to `DEMO_MODE=true`, and points the built frontend at it via
// `CARDINAL_API_PORT` -- exactly as gates 7/8/11/12 do.
export default defineConfig({
  testDir: "./tests",
  testMatch: "cart.spec.ts",
  // One shared backend, one in-memory cart store, and a deliberately serial chain
  // (`cart.spec.ts`'s own note) -- concurrent workers would race the same account's cart.
  fullyParallel: false,
  workers: 1,
  reporter: [["json", { outputFile: "test-results/cart.json" }], ["list"]],
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
