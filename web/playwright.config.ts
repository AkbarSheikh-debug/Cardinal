import { defineConfig } from "@playwright/test";

// Gate 6.2: golden-message fixtures render in a headless browser with zero console
// errors/warnings. `webServer` builds+serves the real app (not a dev server with HMR noise)
// so what Playwright loads is what a deploy would actually ship.
//
// `testMatch` is deliberately narrow: `web/tests/` also holds `mcp-apps.spec.ts` (gate 7,
// `playwright.mcp-apps.config.ts`), which needs a real Python backend this config's `webServer`
// never starts. Without this, Playwright's default file discovery picks up *both* spec files
// here and gate 6.2 fails on tests that were never its own.
export default defineConfig({
  testDir: "./tests",
  testMatch: "render.spec.ts",
  fullyParallel: true,
  reporter: [["list"]],
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
