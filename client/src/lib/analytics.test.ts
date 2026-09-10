import posthog from "posthog-js"
import { initAnalytics } from "./analytics"

vi.mock("posthog-js", () => ({
  default: { init: vi.fn() },
}))

describe("initAnalytics", () => {
  beforeEach(() => {
    vi.unstubAllEnvs()
    vi.clearAllMocks()
  })

  it("does not initialise PostHog when no key is configured", () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "")
    initAnalytics()
    expect(posthog.init).not.toHaveBeenCalled()
  })

  it("sends events through the first-party reverse proxy by default", () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test_key")
    initAnalytics()
    expect(posthog.init).toHaveBeenCalledWith(
      "phc_test_key",
      expect.objectContaining({ api_host: "https://d.distilledmetrics.com" })
    )
  })

  it("points UI links back at PostHog rather than the proxy", () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test_key")
    initAnalytics()
    expect(posthog.init).toHaveBeenCalledWith(
      "phc_test_key",
      expect.objectContaining({ ui_host: "https://eu.posthog.com" })
    )
  })

  it("stays cookieless and never builds person profiles", () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test_key")
    initAnalytics()
    expect(posthog.init).toHaveBeenCalledWith(
      "phc_test_key",
      expect.objectContaining({
        cookieless_mode: "always",
        person_profiles: "identified_only",
      })
    )
  })

  it("captures pageviews on load and on SPA route changes", () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test_key")
    initAnalytics()
    expect(posthog.init).toHaveBeenCalledWith(
      "phc_test_key",
      expect.objectContaining({
        capture_pageview: "history_change",
        capture_pageleave: true,
      })
    )
  })

  it("uses the configured host override when provided", () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test_key")
    vi.stubEnv("VITE_POSTHOG_HOST", "https://ph.example.com")
    initAnalytics()
    expect(posthog.init).toHaveBeenCalledWith(
      "phc_test_key",
      expect.objectContaining({ api_host: "https://ph.example.com" })
    )
  })
})
