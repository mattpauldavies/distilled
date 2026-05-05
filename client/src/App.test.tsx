import { render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse, delay } from "msw"
import type { ReactNode } from "react"
import { server } from "@/test/mocks/server"
import { makeRepo } from "@/test/factories"
import App from "./App"

let signedIn = true

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token", isSignedIn: signedIn }),
  useClerk: () => ({ signOut: vi.fn() }),
  SignedIn: ({ children }: { children: ReactNode }) => (signedIn ? <>{children}</> : null),
  SignedOut: ({ children }: { children: ReactNode }) => (signedIn ? null : <>{children}</>),
  SignIn: () => <div data-testid="clerk-sign-in" />,
}))

vi.mock("@/components/Dashboard", () => ({
  Dashboard: ({ repos }: { repos: { id: string; full_name: string }[] }) => (
    <div data-testid="dashboard">dashboard for {repos.map((r) => r.full_name).join(",")}</div>
  ),
}))

describe("App", () => {
  beforeEach(() => {
    signedIn = true
  })

  it("shows the sign-in page when signed out", () => {
    signedIn = false
    render(<App />)
    expect(screen.getByTestId("clerk-sign-in")).toBeInTheDocument()
    expect(screen.queryByText(/Initialising/i)).not.toBeInTheDocument()
  })

  it("shows Initialising while repos are loading", async () => {
    server.use(
      http.get("/repos", async () => {
        await delay(50)
        return HttpResponse.json({ items: [makeRepo()], total: 1, offset: 0, limit: 100 })
      })
    )

    render(<App />)

    expect(screen.getByText(/Initialising/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByTestId("dashboard")).toBeInTheDocument()
    })
  })

  it("shows the error screen when repos fails", async () => {
    server.use(http.get("/repos", () => new HttpResponse(null, { status: 500 })))

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText("Failed to fetch repos: 500")).toBeInTheDocument()
    })
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument()
  })

  it("shows onboarding when no repos", async () => {
    server.use(
      http.get("/repos", () => HttpResponse.json({ items: [], total: 0, offset: 0, limit: 100 }))
    )

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText("Welcome to Distilled")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument()
  })

  it("renders the dashboard when repos are loaded", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId("dashboard")).toBeInTheDocument()
    })
  })
})
