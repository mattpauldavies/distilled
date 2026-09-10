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

  it("initialises PostHog in cookieless mode when a key is configured", () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test_key")
    initAnalytics()
    expect(posthog.init).toHaveBeenCalledWith(
      "phc_test_key",
      expect.objectContaining({
        api_host: "https://eu.i.posthog.com",
        cookieless_mode: "always",
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
