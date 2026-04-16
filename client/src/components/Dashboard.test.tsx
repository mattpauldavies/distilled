import { render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse, delay } from "msw"
import { server } from "@/test/mocks/server"
import { Dashboard } from "./Dashboard"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token" }),
  useClerk: () => ({ signOut: vi.fn() }),
}))

// Mock chart components — Canvas doesn't work in jsdom
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

describe("Dashboard", () => {
  it("renders metric cards with data", async () => {
    render(<Dashboard />)

    // Deployment frequency: deploys_per_week 4.2 → "4.2"
    await waitFor(() => {
      expect(screen.getByText("4.2")).toBeInTheDocument()
    })

    // Lead time: median_seconds 7200 = 2h
    expect(screen.getByText("2h")).toBeInTheDocument()
    // Cycle time: median_seconds 3600 = 1h
    expect(screen.getByText("1h")).toBeInTheDocument()
    // Throughput: prs_per_engineer_per_month 5.0 → "5.0"
    expect(screen.getByText("5.0")).toBeInTheDocument()
    // Open PRs
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("5 live · 2 draft")).toBeInTheDocument()
  })

  it("shows loading state while metrics load", async () => {
    server.use(
      http.get("/metrics/unified", async () => {
        await delay(100)
        return HttpResponse.json({
          deployment_frequency: {
            status: "ok",
            total: 1,
            days: 30,
            daily_counts: [],
            deploys_per_week: 1.0,
          },
          lead_time: { status: "ok", weekly: [], median_seconds: null },
          pr_cycle_time: { status: "ok", weekly: [], median_seconds: null },
          throughput: {
            weekly: [],
            total_prs: null,
            unique_authors: null,
            prs_per_engineer_per_month: null,
          },
          open_prs: { total: 0, live: 0, draft: 0 },
          pr_ageing: { buckets: [] },
          data_quality: {
            attribution_coverage_percent: null,
            freshness: { status: "ok", last_refresh_at: null },
            setup: { has_production_environment: false, production_environments: [] },
          },
        })
      })
    )

    render(<Dashboard />)

    // Wait for repos to load, which triggers metrics fetch with loading=true
    await waitFor(() => {
      expect(screen.getByText("Deployment Frequency")).toBeInTheDocument()
    })

    // Once metrics resolve, deployment frequency appears as deploys_per_week
    await waitFor(() => {
      expect(screen.getByText("1.0")).toBeInTheDocument()
    })
  })

  it("shows onboarding screen when no repos", async () => {
    server.use(
      http.get("/repos", () => {
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 100 })
      })
    )

    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByText("Welcome to Distilled")).toBeInTheDocument()
    })
  })

  it("shows repos error banner", async () => {
    server.use(
      http.get("/repos", () => {
        return new HttpResponse(null, { status: 500 })
      })
    )

    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByText("Failed to fetch repos: 500")).toBeInTheDocument()
    })
  })

  it("shows metrics error with retry button", async () => {
    server.use(
      http.get("/metrics/unified", () => {
        return new HttpResponse(null, { status: 500 })
      })
    )

    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByText("Failed to load metrics: 500")).toBeInTheDocument()
    })
    expect(screen.getByText("Retry")).toBeInTheDocument()
  })

  it("shows sign out button", async () => {
    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByText("Sign out")).toBeInTheDocument()
    })
  })
})
