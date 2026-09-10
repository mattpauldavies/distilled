import posthog from "posthog-js"

const DEFAULT_HOST = "https://d.distilledmetrics.com"

const UI_HOST = "https://eu.posthog.com"

/**
 * Initialise PostHog product analytics in cookieless mode.
 *
 * Uses PostHog's server-side hash mode ("cookieless_mode: always"), which
 * stores nothing on the user's device — no cookies, localStorage, or
 * sessionStorage — so no cookie consent banner is required. Events are
 * anonymous; identify() is intentionally never called.
 *
 * No-op when VITE_POSTHOG_KEY is unset (local dev, tests).
 */
export function initAnalytics(): void {
  const key = import.meta.env.VITE_POSTHOG_KEY ?? ""
  if (!key) return

  posthog.init(key, {
    api_host: import.meta.env.VITE_POSTHOG_HOST ?? DEFAULT_HOST,
    ui_host: UI_HOST,
    cookieless_mode: "always",
    // Cookieless mode never identifies anyone, so no person profile is ever
    // created. Stating it explicitly keeps anonymous events out of person
    // processing entirely.
    person_profiles: "identified_only",
    defaults: "2026-05-30",
  })
}
