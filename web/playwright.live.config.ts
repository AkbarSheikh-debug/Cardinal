import { defineConfig } from "@playwright/test";

// The live-path smoke test (`tests/live-chat.spec.ts`). Unlike every other Playwright config
// here, this one starts no server: it drives the *running* `docker compose up` stack on :5173,
// because what it is checking is precisely that the deployed image works -- the four defects
// D-052/D-053/D-054 name were all invisible to a config that builds its own server from source.
//
// Needs DEMO_MODE=false and a real ANTHROPIC_API_KEY, and it spends real tokens, so it is
// deliberately not part of `make verify` or any phase gate (D-015's boundary, unchanged).
export default defineConfig({
  testDir: "./tests",
  testMatch: ["live-chat.spec.ts", "model-picker.spec.ts"],
  reporter: [["list"]],
  timeout: 600_000,
  use: {
    baseURL: "http://localhost:5173",
    viewport: { width: 1440, height: 900 },
  },
});
