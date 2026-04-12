/**
 * Playwright global setup — authenticates the smoke test user via Clerk.
 *
 * Requires:
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
 * This setup uses Clerk's sign-in token API to sign in the test user without
 * any browser UI interaction, then saves the resulting session as storageState
 * so all test workers start pre-authenticated.
 */

import { chromium, FullConfig } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

export const AUTH_FILE = path.join(__dirname, ".auth/user.json");

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const secretKey = process.env.CLERK_SECRET_KEY;
  const userId = process.env.CLERK_SMOKE_USER_ID;
  const baseUrl = process.env.SMOKE_BASE_URL ?? "http://localhost:5173";

  if (!secretKey || !userId) {
    throw new Error(
      "CLERK_SECRET_KEY and CLERK_SMOKE_USER_ID must be set to run smoke tests.\n" +
        "See e2e/global-setup.ts for setup instructions.",
    );
  }

  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });

  // 1. Create a one-time sign-in token for the test user via Clerk Backend API
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

  // 2. Navigate to the sign-in URL in a headless browser.
  //    Clerk processes the token, establishes a session, and redirects to the app.
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto(signInUrl);

  // Wait for Clerk to redirect back to the app after processing the token
  await page.waitForURL(`${baseUrl}*`, { timeout: 30_000 });

  // Wait for the dashboard to be ready — confirms auth + API round-trip both worked
  await page.waitForSelector('[role="combobox"]', { timeout: 30_000 });

  // 3. Save the authenticated browser state for all test workers
  await context.storageState({ path: AUTH_FILE });
  await browser.close();
}
