/**
 * Playwright global setup — authenticates the smoke test user via Clerk.
 *
 * Requires:
 *   CLERK_PUBLISHABLE_KEY — Clerk publishable key (pk_test_...)
 *   CLERK_SECRET_KEY      — Clerk backend API key (sk_test_...)
 *   CLERK_SMOKE_USER_ID   — Clerk user ID of the pre-created smoke test user
 *   SMOKE_BASE_URL        — app base URL (default: http://localhost:5173)
 *
 * One-time Clerk Dashboard setup:
 *   1. Create a test user (any email, no GitHub OAuth required)
 *   2. Note their user ID (e.g. user_abc123) → set as CLERK_SMOKE_USER_ID
 *   3. Add http://localhost:5173 to Allowed Redirect URLs
 *   4. Set After Sign-in URL to http://localhost:5173 (or match SMOKE_BASE_URL)
 *
 * Auth strategy:
 *   1. clerkSetup() fetches a short-lived Testing Token from the Clerk Backend
 *      API and stores it in process.env.CLERK_TESTING_TOKEN.
 *   2. A one-time sign-in URL is created for the smoke test user.
 *   3. The Testing Token is appended to that URL as __clerk_testing_token so
 *      Clerk's bot-detection is satisfied on the server side before any
 *      redirect happens.
 *   4. The browser navigates to the patched URL, Clerk sets the session, and
 *      redirects back to the app.
 *   5. The resulting session is saved as storageState so all test workers
 *      start pre-authenticated.
 */

import { clerkSetup } from "@clerk/testing/playwright";
import { chromium, FullConfig } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

export const AUTH_FILE = path.join(__dirname, ".auth/user.json");

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const secretKey = process.env.CLERK_SECRET_KEY;
  const userId = process.env.CLERK_SMOKE_USER_ID;
  const baseUrl = process.env.SMOKE_BASE_URL ?? "http://localhost:5173";

  if (!process.env.CLERK_PUBLISHABLE_KEY || !secretKey || !userId) {
    throw new Error(
      "CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY and CLERK_SMOKE_USER_ID must be set to run smoke tests.\n" +
        "See e2e/global-setup.ts for setup instructions.",
    );
  }

  // Fetch a Testing Token from Clerk's Backend API and store it in
  // process.env.CLERK_TESTING_TOKEN so we can append it to FAPI requests.
  await clerkSetup();

  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });

  // Create a one-time sign-in URL for the test user via Clerk Backend API.
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
  // bot-detection is bypassed on the direct FAPI navigation. This is the
  // correct approach for server-side redirects — setupClerkTestingToken() is
  // designed for XHR interception inside a loaded app, not for navigation
  // requests to Clerk's own domain.
  const patchedUrl = new URL(signInUrl);
  const testingToken = process.env.CLERK_TESTING_TOKEN;
  if (testingToken) {
    patchedUrl.searchParams.set("__clerk_testing_token", testingToken);
  }

  // Navigate to the patched sign-in URL. Clerk processes the ticket, sets the
  // session cookie, and redirects to baseUrl.
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto(patchedUrl.toString());

  // Wait for Clerk to redirect back to the app after processing the token.
  await page.waitForURL(`${baseUrl}*`, { timeout: 30_000 });

  // Wait for the dashboard to be ready — confirms auth + API round-trip worked.
  await page.waitForSelector('[role="combobox"]', { timeout: 30_000 });

  // Save the authenticated browser state for all test workers.
  await context.storageState({ path: AUTH_FILE });
  await browser.close();
}
