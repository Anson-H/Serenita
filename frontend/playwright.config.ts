import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  outputDir: "test-results/browser",
  fullyParallel: true,
  workers: 4,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4175",
    viewport: { width: 1280, height: 900 },
    contextOptions: { reducedMotion: "reduce" },
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", testMatch: /conversation-(overlay-geometry|scroll-controller|new-chat)\.spec\.ts/, use: {
      ...devices["Desktop Safari"],
      // Enable full keyboard navigation for this test process, never the user's system preferences.
      launchOptions: process.platform === "darwin" ? {
        ignoreDefaultArgs: true,
        args: ["--inspector-pipe", "--headless", "--no-startup-window", "-AppleKeyboardUIMode", "2"]
      } : {}
    } }
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4175 --strictPort",
    url: "http://127.0.0.1:4175/",
    reuseExistingServer: false
  }
});
