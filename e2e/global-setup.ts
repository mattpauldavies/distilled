/**
 * Playwright global setup — authenticates the smoke test user via Clerk.
 *
 * Requires:
 *   VITE_CLERK_PUBLISHABLE_KEY — Clerk publishable key (pk_test_...)
 *   CLERK_SECRET_KEY           — Clerk backend API key (sk_test_...)
 *   CLERK_SMOKE_USER_EMAIL     — email address of the smoke test user
 *   SMOKE_BASE_URL             — app base URL (default: http://localhost:5173)
 *
 * One-time Clerk Dashboard setup:
 *   1. Create a test user with a verified email address
 *   2. Set CLERK_SMOKE_USER_EMAIL to that email address
 *
 * Auth strategy:
 *   1. clerkSetup() fetches a Testing Token from the Clerk Backend API and
 *      stores it in process.env (CLERK_FAPI, CLERK_TESTING_TOKEN). These env
 *      vars are inherited by Playwright worker processes for per-test bot
 *      detection bypass via setupClerkTestingToken().
 *   2. The browser navigates to the app, Clerk JS loads, and clerk.signIn()
 *      signs in programmatically via the ticket strategy.
 *   3. The resulting session is saved as storageState so all test workers
 *      start pre-authenticated.
 */

import { clerkSetup, clerk } from "@clerk/testing/playwright";
import { chromium, FullConfig } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

export const AUTH_FILE = path.join(__dirname, ".auth/user.json");

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const secretKey = process.env.CLERK_SECRET_KEY;
  const email = process.env.CLERK_SMOKE_USER_EMAIL;
  const baseUrl = process.env.SMOKE_BASE_URL ?? "http://localhost:5173";

  // clerkSetup() checks VITE_CLERK_PUBLISHABLE_KEY (and other framework
  // prefixes) automatically, so accept either name in our own guard.
  const publishableKey =
    process.env.CLERK_PUBLISHABLE_KEY ??
    process.env.VITE_CLERK_PUBLISHABLE_KEY;

  if (!publishableKey || !secretKey || !email) {
    throw new Error(
      "A Clerk publishable key (CLERK_PUBLISHABLE_KEY or VITE_CLERK_PUBLISHABLE_KEY), " +
        "CLERK_SECRET_KEY and CLERK_SMOKE_USER_EMAIL must be set to run smoke tests.\n" +
        "See e2e/global-setup.ts for setup instructions.",
    );
  }

  // Fetch a Testing Token from Clerk's Backend API. This sets
  // process.env.CLERK_FAPI and process.env.CLERK_TESTING_TOKEN which are
  // inherited by test workers for setupClerkTestingToken().
  await clerkSetup();

  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });

  // Launch browser and navigate to the app so Clerk JS loads.
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto(baseUrl);

  // clerk.signIn() internally calls setupClerkTestingToken() to bypass bot
  // detection, waits for window.Clerk to load, looks up the user by email,
  // creates a sign-in token, then signs in via the ticket strategy.
  await clerk.signIn({ page, emailAddress: email });

  // Wait for the dashboard to be ready — confirms auth + API round-trip worked.
  await page.waitForSelector('[role="combobox"]', { timeout: 30_000 });

  // Save the authenticated browser state for all test workers.
  await context.storageState({ path: AUTH_FILE });
  await browser.close();
}
