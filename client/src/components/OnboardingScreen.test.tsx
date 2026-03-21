import { render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { OnboardingScreen } from "./OnboardingScreen"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token" }),
}))

describe("OnboardingScreen", () => {
  it("renders welcome heading and install CTA", () => {
    render(<OnboardingScreen onReposDetected={vi.fn()} />)

    expect(screen.getByText("Welcome to Distilled")).toBeInTheDocument()
    expect(screen.getByText("Install GitHub App →")).toBeInTheDocument()
    expect(screen.getByText(/Already installed/)).toBeInTheDocument()
  })

  it("install button has correct GitHub App URL", () => {
    render(<OnboardingScreen onReposDetected={vi.fn()} />)

    const installLink = screen.getByRole("link", { name: /Install GitHub App/ })
    expect(installLink).toHaveAttribute("href", "https://github.com/apps/test-app/installations/new")
  })

  it("calls onReposDetected when polling detects repos", async () => {
    const onReposDetected = vi.fn()

    server.use(
      http.get("/api/repos", () => {
        return HttpResponse.json({
          items: [{ id: "repo-1", full_name: "org/repo", default_branch: "main" }],
          total: 1,
          offset: 0,
          limit: 1,
        })
      })
    )

    // Use a very short poll interval so the test completes quickly without fake timers
    render(<OnboardingScreen onReposDetected={onReposDetected} pollIntervalMs={50} />)

    await waitFor(() => {
      expect(onReposDetected).toHaveBeenCalledOnce()
    })
  })

  it("does not call onReposDetected when repos list is empty", async () => {
    const onReposDetected = vi.fn()

    server.use(
      http.get("/api/repos", () => {
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 1 })
      })
    )

    render(<OnboardingScreen onReposDetected={onReposDetected} pollIntervalMs={50} />)

    // Wait two poll intervals and confirm callback was not called
    await new Promise((r) => setTimeout(r, 150))

    expect(onReposDetected).not.toHaveBeenCalled()
  })
})
