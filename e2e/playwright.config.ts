import { defineConfig, devices } from "@playwright/test";

/**
 * Base URL defaults to local dev client. Override for pre/post-deploy checks:
 *   SMOKE_BASE_URL=https://app.example.com npx playwright test
 */
export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? "http://localhost:5173",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
