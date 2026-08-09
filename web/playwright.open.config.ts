import { defineConfig } from "@playwright/test";

// Not a gate: a driver for looking at the *running* `docker compose up` stack, so what gets
// screenshotted is the real deployed app behind nginx (including the `/auth/` proxy block)
// rather than a dev server. No `webServer` entry -- it points at whatever is already up.
export default defineConfig({
  testDir: "./tests",
  testMatch: "open-app.spec.ts",
  fullyParallel: false,
  reporter: [["list"]],
  // Both themes, at a wide viewport. The bugs D-086 records were invisible at 1360px in light
  // mode and obvious at 2000px in dark -- capturing only one combination is how they shipped.
  projects: [
    {
      name: "dark",
      use: { colorScheme: "dark", viewport: { width: 2000, height: 1100 } },
    },
    {
      name: "light",
      use: { colorScheme: "light", viewport: { width: 1440, height: 900 } },
    },
  ],
  use: {
    baseURL: process.env.CARDINAL_APP_URL || "http://localhost:5173",
  },
});
