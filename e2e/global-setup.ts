/**
 * Playwright global setup — authenticates the smoke test user via Clerk.
 *
 * Requires:
 *   VITE_CLERK_PUBLISHABLE_KEY — Clerk publishable key (pk_test_...)
 *   CLERK_SECRET_KEY           — Clerk backend API key (sk_test_...)
 *   CLERK_SMOKE_USER_ID        — Clerk user ID of the pre-created smoke test user
 *   SMOKE_BASE_URL             — app base URL (default: http://localhost:5173)
 *
 * One-time Clerk Dashboard setup:
 *   1. Create a test user (any email, no GitHub OAuth required)
 *   2. Note their user ID (e.g. user_abc123) → set as CLERK_SMOKE_USER_ID
 *
 * Auth strategy:
 *   1. clerkSetup() fetches a Testing Token from the Clerk Backend API and
 *      stores it in process.env (CLERK_FAPI, CLERK_TESTING_TOKEN). These env
 *      vars are inherited by Playwright worker processes for per-test bot
 *      detection bypass via setupClerkTestingToken().
 *   2. A one-time sign-in URL is created for the smoke test user via the
 *      Clerk Backend API.
 *   3. setupClerkTestingToken() is applied to the browser context so Clerk
 *      Frontend API requests include the testing token.
 *   4. The browser navigates to the sign-in URL (with __clerk_testing_token
 *      appended for the initial server-side request). Clerk verifies the
 *      ticket server-side, sets the session, and redirects to the app.
 *   5. The resulting session is saved as storageState so all test workers
 *      start pre-authenticated.
 */

import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright";
import { chromium, FullConfig } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

export const AUTH_FILE = path.join(__dirname, ".auth/user.json");

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const secretKey = process.env.CLERK_SECRET_KEY;
  const userId = process.env.CLERK_SMOKE_USER_ID;
  const baseUrl = process.env.SMOKE_BASE_URL ?? "http://localhost:5173";

  // clerkSetup() checks VITE_CLERK_PUBLISHABLE_KEY (and other framework
  // prefixes) automatically, so accept either name in our own guard.
  const publishableKey =
    process.env.CLERK_PUBLISHABLE_KEY ??
    process.env.VITE_CLERK_PUBLISHABLE_KEY;

  if (!publishableKey || !secretKey || !userId) {
    throw new Error(
      "A Clerk publishable key (CLERK_PUBLISHABLE_KEY or VITE_CLERK_PUBLISHABLE_KEY), " +
        "CLERK_SECRET_KEY and CLERK_SMOKE_USER_ID must be set to run smoke tests.\n" +
        "See e2e/global-setup.ts for setup instructions.",
    );
  }

  // Fetch a Testing Token from Clerk's Backend API. This sets
  // process.env.CLERK_FAPI and process.env.CLERK_TESTING_TOKEN which are
  // inherited by test workers for setupClerkTestingToken().
  await clerkSetup();

  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });

  // Create a one-time sign-in URL for the test user via Clerk Backend API.
  // We pass redirect_url so Clerk redirects back to the app after verifying
  // the ticket server-side. This avoids the client-side signIn.create() flow
  // which requires the user to have an identification (email/phone).
  const tokenResponse = await fetch("https://api.clerk.com/v1/sign_in_tokens", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secretKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ user_id: userId, redirect_url: baseUrl }),
  });

  if (!tokenResponse.ok) {
    const body = await tokenResponse.text();
    throw new Error(
      `Clerk sign-in token creation failed (${tokenResponse.status}): ${body}`,
    );
  }

  const { url: signInUrl } = (await tokenResponse.json()) as { url: string };

  // Append the Testing Token to the sign-in URL so Clerk's server-side
  // bot-detection is bypassed on the initial navigation to Clerk's domain.
  const patchedUrl = new URL(signInUrl);
  const testingToken = process.env.CLERK_TESTING_TOKEN;
  if (testingToken) {
    patchedUrl.searchParams.set("__clerk_testing_token", testingToken);
  }

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  // Set up testing token interception on the context so that Clerk Frontend
  // API requests (session validation etc.) after the redirect also include
  // the testing token. This is critical for bot-detection bypass.
  await setupClerkTestingToken({ page });

  // Navigate to the sign-in URL. Clerk verifies the ticket server-side,
  // creates the session, and redirects to baseUrl.
  await page.goto(patchedUrl.toString());

  // Wait for Clerk to redirect back to the app after processing the token.
  await page.waitForURL(`${baseUrl}**`, { timeout: 30_000 });

  // Wait for the dashboard to be ready — confirms auth + API round-trip worked.
  await page.waitForSelector('[role="combobox"]', { timeout: 30_000 });

  // Save the authenticated browser state for all test workers.
  await context.storageState({ path: AUTH_FILE });
  await browser.close();
}
