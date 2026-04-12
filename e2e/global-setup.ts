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
 *   1. Create a test user (any name, no OAuth required)
 *   2. Note their user ID (e.g. user_abc123) → set as CLERK_SMOKE_USER_ID
 *      (an email address is provisioned automatically if missing)
 *
 * Auth strategy:
 *   1. clerkSetup() fetches a Testing Token from the Clerk Backend API and
 *      stores it in process.env (CLERK_FAPI, CLERK_TESTING_TOKEN). These env
 *      vars are inherited by Playwright worker processes for per-test bot
 *      detection bypass via setupClerkTestingToken().
 *   2. The smoke test user is checked for an email address. If none exists,
 *      a verified email is created via the Backend API (required for Clerk's
 *      client-side ticket sign-in strategy).
 *   3. The browser navigates to the app, Clerk JS loads, and clerk.signIn()
 *      signs in programmatically via the ticket strategy.
 *   4. The resulting session is saved as storageState so all test workers
 *      start pre-authenticated.
 */

import { clerkSetup, clerk } from "@clerk/testing/playwright";
import { chromium, FullConfig } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

export const AUTH_FILE = path.join(__dirname, ".auth/user.json");

/** Clerk Backend API helper — GET/POST with Bearer auth. */
async function clerkApi(
  path: string,
  secretKey: string,
  options?: { method?: string; body?: Record<string, unknown> },
): Promise<Response> {
  return fetch(`https://api.clerk.com${path}`, {
    method: options?.method ?? "GET",
    headers: {
      Authorization: `Bearer ${secretKey}`,
      ...(options?.body ? { "Content-Type": "application/json" } : {}),
    },
    ...(options?.body ? { body: JSON.stringify(options.body) } : {}),
  });
}

/**
 * Ensure the smoke test user has at least one verified email address.
 * Clerk's client-side ticket sign-in strategy requires an "identification"
 * (email/phone/username). Returns the user's email address.
 */
async function ensureUserEmail(
  userId: string,
  secretKey: string,
): Promise<string> {
  const resp = await clerkApi(`/v1/users/${userId}`, secretKey);
  if (!resp.ok) {
    throw new Error(
      `Failed to fetch smoke test user ${userId}: ${await resp.text()}`,
    );
  }

  const user = (await resp.json()) as {
    email_addresses: Array<{ email_address: string }>;
  };

  if (user.email_addresses.length > 0) {
    return user.email_addresses[0].email_address;
  }

  // No email — create a verified one so the ticket strategy works.
  const addResp = await clerkApi(`/v1/email_addresses`, secretKey, {
    method: "POST",
    body: {
      user_id: userId,
      email_address: `smoke-test+${userId}@test.distilled.dev`,
      verified: true,
      primary: true,
    },
  });

  if (!addResp.ok) {
    throw new Error(
      `Failed to add email to smoke test user: ${await addResp.text()}`,
    );
  }

  const created = (await addResp.json()) as { email_address: string };
  return created.email_address;
}

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

  // Ensure the smoke test user has a verified email (required for ticket
  // sign-in strategy which needs at least one identification).
  const email = await ensureUserEmail(userId, secretKey);

  // Launch browser and navigate to the app so Clerk JS loads.
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto(baseUrl);

  // clerk.signIn() internally calls setupClerkTestingToken() to bypass bot
  // detection, waits for window.Clerk to load, then signs in via the ticket
  // strategy (Backend API creates a sign-in token, client-side calls
  // window.Clerk.signIn.create({ strategy: 'ticket', ticket })).
  await clerk.signIn({ page, emailAddress: email });

  // Wait for the dashboard to be ready — confirms auth + API round-trip worked.
  await page.waitForSelector('[role="combobox"]', { timeout: 30_000 });

  // Save the authenticated browser state for all test workers.
  await context.storageState({ path: AUTH_FILE });
  await browser.close();
}
