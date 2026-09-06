import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/integration",
  testMatch: "*.spec.ts",
  workers: 1,
  outputDir: "test-results/integration",
  retries: 0,
  reporter: "list",
  use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:4176", trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    { command: "../.venv/bin/python tests/integration/backend.py", url: "http://127.0.0.1:8186/api/auth/session", reuseExistingServer: false, gracefulShutdown: { signal: "SIGTERM", timeout: 35000 } },
    { command: "npm run dev -- --config tests/integration/vite.config.ts", url: "http://127.0.0.1:4176", reuseExistingServer: false }
  ]
});
