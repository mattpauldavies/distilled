/**
 * Smoke tests for Distilled — browser-driven via Playwright.
 *
 * Requires the full stack running (DB + server + client) with demo data seeded:
 *   make db-up && make migrate && make seed-demo
 *   make dev
 *   # then in another terminal:
 *   make smoke-test
 *
 * To target a deployed environment:
 *   SMOKE_BASE_URL=https://app.example.com make smoke-test
 *
 * Focus: metric accuracy. The demo seed is deterministic so several values
 * are exact — in particular the open PR counts and live/draft split which are
 * fully stable regardless of when the seed was run.
 */

import { expect, Page, test } from "@playwright/test";

// ── Known seed values ─────────────────────────────────────────────────────────
// From server/scripts/seed_demo.py — these never change once seeded.

const API_OPEN_TOTAL = 10;
const API_OPEN_LIVE = 8;
const API_OPEN_DRAFT = 2;

const WEB_OPEN_TOTAL = 12;
const WEB_OPEN_LIVE = 9;
const WEB_OPEN_DRAFT = 3;

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Navigate to the dashboard and wait until metric data has loaded.
 * We wait for the Open PRs caption which is only rendered once the API
 * response arrives — this is the most reliable "data is ready" signal.
 */
async function loadDashboard(page: Page): Promise<void> {
  await page.goto("/");
  // Repos load first; wait for the first repo to appear in the selector
  await expect(page.getByRole("combobox")).not.toHaveText("Select a repository", {
    timeout: 15_000,
  });
  // Then wait for metric data — the Open PRs caption confirms the API responded
  await expect(page.getByText(/live · \d+ draft/)).toBeVisible({
    timeout: 15_000,
  });
}

/**
 * Select a repo by its full_name from the Radix UI Select.
 */
async function selectRepo(page: Page, fullName: string): Promise<void> {
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: fullName }).click();
  // Wait for metrics to reload
  await expect(page.getByText(/live · \d+ draft/)).toBeVisible({
    timeout: 10_000,
  });
}

/**
 * Return a locator scoped to a MetricCard by its title text.
 * Titles are rendered as plain text (CSS uppercasing is visual only).
 */
function metricCard(page: Page, title: string) {
  return page.locator('[data-slot="card"]').filter({ hasText: title });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe("Page structure", () => {
  test("dashboard renders key sections", async ({ page }) => {
    await loadDashboard(page);
    await expect(page.getByRole("heading", { name: /Key Metrics/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Trends/i })).toBeVisible();
  });

  test("no error alerts on load", async ({ page }) => {
    await loadDashboard(page);
    await expect(page.getByRole("alert")).not.toBeVisible();
  });
});

test.describe("Repository selector", () => {
  test("lists both demo repos", async ({ page }) => {
    await loadDashboard(page);
    await page.getByRole("combobox").click();
    await expect(page.getByRole("option", { name: "acme-corp/api" })).toBeVisible();
    await expect(page.getByRole("option", { name: "acme-corp/web" })).toBeVisible();
  });

  test("defaults to acme-corp/api (first alphabetically)", async ({ page }) => {
    await loadDashboard(page);
    await expect(page.getByRole("combobox")).toHaveText("acme-corp/api");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "acme-corp/api",
    );
  });
});

test.describe("Open PRs — exact seed counts", () => {
  test("acme-corp/api: correct total and live/draft split", async ({ page }) => {
    await loadDashboard(page);
    const card = metricCard(page, "Open PRs");
    await expect(card.getByText(String(API_OPEN_TOTAL))).toBeVisible();
    await expect(
      card.getByText(`${API_OPEN_LIVE} live · ${API_OPEN_DRAFT} draft`),
    ).toBeVisible();
  });

  test("acme-corp/web: correct total and live/draft split", async ({ page }) => {
    await loadDashboard(page);
    await selectRepo(page, "acme-corp/web");
    const card = metricCard(page, "Open PRs");
    await expect(card.getByText(String(WEB_OPEN_TOTAL))).toBeVisible();
    await expect(
      card.getByText(`${WEB_OPEN_LIVE} live · ${WEB_OPEN_DRAFT} draft`),
    ).toBeVisible();
  });
});

test.describe("Metric cards — no empty or setup-required states", () => {
  // These cards require a production environment; the seed creates one for both repos.
  const PROD_ENV_CARDS = ["Deployment Frequency", "Lead Time", "PR Cycle Time"];

  for (const title of PROD_ENV_CARDS) {
    test(`${title} shows a value (not setup-required)`, async ({ page }) => {
      await loadDashboard(page);
      const card = metricCard(page, title);
      await expect(
        card.getByText("Requires a connected production environment"),
      ).not.toBeVisible();
      // Value must not be the empty dash — some real data should be present
      await expect(card.getByText("—")).not.toBeVisible();
    });
  }

  test("Deployment Frequency shows a positive number", async ({ page }) => {
    await loadDashboard(page);
    const card = metricCard(page, "Deployment Frequency");
    // The value is the raw deployment count, e.g. "18"
    const valueText = await card
      .locator("p.text-5xl")
      .innerText();
    const count = parseInt(valueText, 10);
    expect(count).toBeGreaterThan(0);
  });
});

test.describe("Chart panels — data rendered, no empty states", () => {
  test("Deployments chart is visible", async ({ page }) => {
    await loadDashboard(page);
    await expect(
      page.getByRole("img", { name: "Bar chart showing daily deployment counts" }),
    ).toBeVisible();
  });

  test("Lead Time chart is visible", async ({ page }) => {
    await loadDashboard(page);
    await expect(
      page.getByRole("img", {
        name: "Line chart showing weekly lead time: median and 75th percentile in hours",
      }),
    ).toBeVisible();
  });

  test("PR Cycle Time chart is visible", async ({ page }) => {
    await loadDashboard(page);
    await expect(
      page.getByRole("img", {
        name: "Line chart showing weekly PR cycle time: median and 75th percentile in hours",
      }),
    ).toBeVisible();
  });

  test("PR Ageing chart is visible", async ({ page }) => {
    await loadDashboard(page);
    await expect(
      page.getByRole("img", {
        name: "Bar chart showing age distribution of open pull requests",
      }),
    ).toBeVisible();
  });

  test("no 'Connect a production environment' messages shown", async ({ page }) => {
    await loadDashboard(page);
    await expect(
      page.getByText("Connect a production environment to track deployments"),
    ).not.toBeVisible();
    await expect(
      page.getByText("Connect a production environment to track lead time"),
    ).not.toBeVisible();
    await expect(
      page.getByText("Connect a production environment to track cycle time"),
    ).not.toBeVisible();
  });
});

test.describe("Time window toggle", () => {
  test("switching to 7d shows fewer deployments than 90d", async ({ page }) => {
    await loadDashboard(page);

    // Read the deployment count at 90d
    await page.getByRole("button", { name: "90d" }).click();
    await expect(page.getByRole("button", { name: "90d" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // Wait for chart to update
    await page.waitForTimeout(500);
    const count90 = parseInt(
      await metricCard(page, "Deployment Frequency")
        .locator("p.text-5xl")
        .innerText(),
      10,
    );

    // Read the deployment count at 7d
    await page.getByRole("button", { name: "7d" }).click();
    await expect(page.getByRole("button", { name: "7d" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.waitForTimeout(500);
    const count7 = parseInt(
      await metricCard(page, "Deployment Frequency")
        .locator("p.text-5xl")
        .innerText(),
      10,
    );

    expect(count7).toBeLessThanOrEqual(count90);
  });

  test("active window button has aria-pressed=true", async ({ page }) => {
    await loadDashboard(page);
    // Default is 30d
    await expect(page.getByRole("button", { name: "30d" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByRole("button", { name: "7d" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await page.getByRole("button", { name: "7d" }).click();
    await expect(page.getByRole("button", { name: "7d" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByRole("button", { name: "30d" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});

test.describe("Repo switching", () => {
  test("switching repo updates the page title", async ({ page }) => {
    await loadDashboard(page);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "acme-corp/api",
    );
    await selectRepo(page, "acme-corp/web");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "acme-corp/web",
    );
  });

  test("open PR counts update when switching repos", async ({ page }) => {
    await loadDashboard(page);

    // Start on api
    const apiCard = metricCard(page, "Open PRs");
    await expect(apiCard.getByText(String(API_OPEN_TOTAL))).toBeVisible();

    // Switch to web
    await selectRepo(page, "acme-corp/web");
    const webCard = metricCard(page, "Open PRs");
    await expect(webCard.getByText(String(WEB_OPEN_TOTAL))).toBeVisible();
  });
});
