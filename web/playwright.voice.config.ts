import { defineConfig } from "@playwright/test";

// Gate 16.1 (PLAN-02 P16). Its own config, same reason every other gate keeps one.
//
// `--use-fake-device-for-media-capture` gives Chromium a synthetic microphone so push-to-talk
// can be driven without a real one, and the permission is granted up front rather than left to
// a dialog no headless run can click.
export default defineConfig({
  testDir: "./tests",
  testMatch: "voice.spec.ts",
  fullyParallel: false,
  reporter: [["json", { outputFile: "test-results/voice.json" }], ["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    permissions: ["microphone"],
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-capture",
      ],
    },
  },
  webServer: {
    command: "npm run build && npm run preview",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
