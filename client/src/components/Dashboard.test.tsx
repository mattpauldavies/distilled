import { screen, waitFor } from "@testing-library/react"
import { http, HttpResponse, delay } from "msw"
import { server } from "@/test/mocks/server"
import { makeDataQuality, makeDeploymentFrequency, makeOpenPRs, makeRepo } from "@/test/factories"
import { renderWithProviders as render } from "@/test/render"
import { Dashboard } from "./Dashboard"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token", isSignedIn: true }),
  useClerk: () => ({ signOut: vi.fn() }),
  useUser: () => ({
    user: { fullName: "Test User", primaryEmailAddress: { emailAddress: "test@example.com" } },
  }),
}))

vi.mock("./charts/DeploymentChart", () => ({
  DeploymentChart: () => <div data-testid="deployment-chart" />,
}))
vi.mock("./charts/LeadTimeChart", () => ({
  LeadTimeChart: () => <div data-testid="lead-time-chart" />,
}))
vi.mock("./charts/CycleTimeChart", () => ({
  CycleTimeChart: () => <div data-testid="cycle-time-chart" />,
}))
vi.mock("./charts/PRAgeingChart", () => ({
  PRAgeingChart: () => <div data-testid="pr-ageing-chart" />,
}))

const defaultRepos = [makeRepo(), makeRepo({ id: "repo-2", full_name: "org/other-repo" })]

describe("Dashboard", () => {
  it("renders metric cards with data from per-section endpoints", async () => {
    render(<Dashboard repos={defaultRepos} />)

    await waitFor(() => {
      expect(screen.getByText("4.2")).toBeInTheDocument()
    })

    expect(screen.getByText("2h")).toBeInTheDocument()
    expect(screen.getByText("1h")).toBeInTheDocument()
    expect(screen.getByText("5.0")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("5 live · 2 draft")).toBeInTheDocument()
  })

  it("reveals fast tiles before slow ones (progressive loading)", async () => {
    server.use(
      http.get("/metrics/open-prs", () =>
        HttpResponse.json(makeOpenPRs({ total: 9, live: 6, draft: 3 }))
      ),
      http.get("/metrics/deployment-frequency", async () => {
        await delay(80)
        return HttpResponse.json(makeDeploymentFrequency({ deploys_per_week: 9.9 }))
      })
    )

    render(<Dashboard repos={defaultRepos} />)

    // Open PRs resolves immediately
    await waitFor(() => {
      expect(screen.getByText("6 live · 3 draft")).toBeInTheDocument()
    })

    // At this point, deployment frequency should still be loading (skeleton shown,
    // so the "9.9" value isn't rendered yet)
    expect(screen.queryByText("9.9")).not.toBeInTheDocument()

    // Eventually it catches up
    await waitFor(() => {
      expect(screen.getByText("9.9")).toBeInTheDocument()
    })
  })

  it("shows a per-card error state with retry when that section fails", async () => {
    server.use(http.get("/metrics/open-prs", () => new HttpResponse(null, { status: 500 })))

    render(<Dashboard repos={defaultRepos} />)

    // Other cards still render successfully
    await waitFor(() => {
      expect(screen.getByText("4.2")).toBeInTheDocument()
    })

    // Failed card shows its own error + retry
    expect(screen.getByText("Failed to load")).toBeInTheDocument()
    expect(screen.getByText("Retry")).toBeInTheDocument()
  })

  it("renders the profile menu trigger", async () => {
    render(<Dashboard repos={defaultRepos} />)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Account menu" })).toBeInTheDocument()
    })
  })

  it("shows days of data in the freshness indicator", async () => {
    server.use(
      http.get("/metrics/data-quality", () =>
        HttpResponse.json(
          makeDataQuality({
            freshness: {
              status: "ok",
              last_refresh_at: new Date().toISOString(),
              days_of_data: 47,
            },
          })
        )
      )
    )

    render(<Dashboard repos={defaultRepos} />)

    await waitFor(() => {
      expect(screen.getByText(/47 days of data/)).toBeInTheDocument()
    })
  })

  it("falls back to 30d when insufficient data exists for the default window", async () => {
    server.use(
      http.get("/metrics/data-quality", () =>
        HttpResponse.json(
          makeDataQuality({
            freshness: {
              status: "ok",
              last_refresh_at: new Date().toISOString(),
              days_of_data: 12,
            },
          })
        )
      )
    )

    render(<Dashboard repos={defaultRepos} />)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "30d" })).toHaveAttribute("aria-pressed", "true")
    })

    expect(screen.getByRole("button", { name: "90d" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "6m" })).toBeDisabled()
  })
})
