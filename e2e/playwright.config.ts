import { defineConfig, devices } from "@playwright/test";
import { AUTH_FILE } from "./global-setup";

/**
 * Base URL defaults to local dev client. Override for pre/post-deploy checks:
 *   SMOKE_BASE_URL=https://app.example.com npx playwright test
 */
export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  timeout: 90_000,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  globalSetup: "./global-setup.ts",
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? "http://localhost:5173",
    storageState: AUTH_FILE,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    navigationTimeout: 60_000,
    actionTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
