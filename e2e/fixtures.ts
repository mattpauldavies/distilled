/**
 * Custom Playwright fixtures that set up Clerk's testing token bypass.
 *
 * Each test worker gets a fresh browser context with storageState (from
 * global-setup). But Clerk's Frontend API requests still need the testing
 * token appended to bypass bot detection. setupClerkTestingToken() sets up
 * route interception on the context to handle this automatically.
 *
 * Import { test, expect } from this file instead of @playwright/test.
 */

import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { test as base } from "@playwright/test";

export const test = base.extend({
  page: async ({ page }, use) => {
    await setupClerkTestingToken({ page });
    await use(page);
  },
});

export { expect, Page } from "@playwright/test";
