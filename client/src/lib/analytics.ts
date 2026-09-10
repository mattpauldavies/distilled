import posthog from "posthog-js"

/**
 * Events are sent through a first-party reverse proxy (a CNAME onto PostHog's
 * managed proxy) rather than straight to `eu.i.posthog.com`. Requests to
 * PostHog's own domains are blocked by most content blockers and by Safari and
 * Firefox tracking protection, which silently drops a large share of events.
 */
const DEFAULT_HOST = "https://d.distilledmetrics.com"

/**
 * Where the PostHog app itself lives. Required whenever `api_host` is a proxy,
 * otherwise in-app links (toolbar, session links) point at the proxy domain.
 */
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
    // Both are implied by the `defaults` preset above, but pageview capture is
    // the thing we actually care about here, so pin it rather than leaving it
    // to an opaque version string. "history_change" also covers SPA routing.
    capture_pageview: "history_change",
    capture_pageleave: true,
  })
}
