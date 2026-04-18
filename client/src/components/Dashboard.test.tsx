import { render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse, delay } from "msw"
import { server } from "@/test/mocks/server"
import { makeOpenPRs, makeDeploymentFrequency } from "@/test/factories"
import { Dashboard } from "./Dashboard"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token" }),
  useClerk: () => ({ signOut: vi.fn() }),
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

describe("Dashboard", () => {
  it("renders metric cards with data from per-section endpoints", async () => {
    render(<Dashboard />)

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

    render(<Dashboard />)

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

  it("shows a single error banner only when all sections fail", async () => {
    server.use(
      http.get("/metrics/deployment-frequency", () => new HttpResponse(null, { status: 500 })),
      http.get("/metrics/lead-time", () => new HttpResponse(null, { status: 500 })),
      http.get("/metrics/pr-cycle-time", () => new HttpResponse(null, { status: 500 })),
      http.get("/metrics/throughput", () => new HttpResponse(null, { status: 500 })),
      http.get("/metrics/open-prs", () => new HttpResponse(null, { status: 500 })),
      http.get("/metrics/pr-ageing", () => new HttpResponse(null, { status: 500 })),
      http.get("/metrics/data-quality", () => new HttpResponse(null, { status: 500 }))
    )

    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByText("Retry")).toBeInTheDocument()
    })
  })

  it("does not show the global error banner when only one section fails", async () => {
    server.use(http.get("/metrics/open-prs", () => new HttpResponse(null, { status: 500 })))

    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByText("4.2")).toBeInTheDocument()
    })

    expect(screen.queryByText("Retry")).not.toBeInTheDocument()
  })

  it("shows sign out button", async () => {
    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByText("Sign out")).toBeInTheDocument()
    })
  })
})
