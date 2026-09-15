import { StrictMode, type ReactNode } from "react"
import { screen, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { renderWithProviders } from "@/test/render"
import { useWorkspaceContext } from "@/lib/workspaceContext"
import { OnboardingScreen } from "./OnboardingScreen"

// Mirrors App's Home: the screen only mounts once the workspace is resolved,
// so isOwner is already true on its first mount.
function WhenWorkspaceReady({ children }: { children: ReactNode }) {
  const { activeWorkspace } = useWorkspaceContext()
  return activeWorkspace ? <>{children}</> : null
}

vi.mock("@clerk/clerk-react", () => {
  const stableGetToken = async () => "test-clerk-token"
  return {
    useAuth: () => ({ getToken: stableGetToken, isSignedIn: true }),
  }
})

describe("OnboardingScreen", () => {
  it("mints an installation intent and links to the returned install URL", async () => {
    let workspaceHeader: string | null = null
    server.use(
      http.post("/installations/intents", ({ request }) => {
        workspaceHeader = request.headers.get("X-Workspace-Id")
        return HttpResponse.json({
          install_url: "https://github.com/apps/test-app/installations/new?state=nonce-1",
        })
      })
    )

    renderWithProviders(<OnboardingScreen onReposDetected={vi.fn()} />)

    expect(await screen.findByText("Welcome to Distilled")).toBeInTheDocument()
    const installLink = await screen.findByRole("link", { name: /Install GitHub App/ })
    expect(installLink).toHaveAttribute(
      "href",
      "https://github.com/apps/test-app/installations/new?state=nonce-1"
    )
    expect(workspaceHeader).toBe("workspace-1")
  })

  it("tells members to ask the workspace owner", async () => {
    server.use(
      http.get("/me/workspaces", () =>
        HttpResponse.json({
          items: [{ id: "workspace-1", name: "Test Workspace", slug: null, role: "member" }],
        })
      )
    )

    renderWithProviders(<OnboardingScreen onReposDetected={vi.fn()} />)

    expect(await screen.findByText(/Ask the workspace owner/)).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Install GitHub App/ })).not.toBeInTheDocument()
  })

  it("calls onReposDetected when polling detects repos, scoped to the workspace", async () => {
    const onReposDetected = vi.fn()
    let workspaceHeader: string | null = null

    server.use(
      http.get("/repos", ({ request }) => {
        workspaceHeader = request.headers.get("X-Workspace-Id")
        return HttpResponse.json({
          items: [{ id: "repo-1", full_name: "org/repo", default_branch: "main" }],
          total: 1,
          offset: 0,
          limit: 1,
        })
      })
    )

    renderWithProviders(<OnboardingScreen onReposDetected={onReposDetected} pollIntervalMs={50} />)

    await waitFor(() => {
      expect(onReposDetected).toHaveBeenCalledOnce()
    })
    expect(workspaceHeader).toBe("workspace-1")
  })

  it("does not call onReposDetected when repos list is empty", async () => {
    const onReposDetected = vi.fn()

    server.use(
      http.get("/repos", () => {
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 1 })
      })
    )

    renderWithProviders(<OnboardingScreen onReposDetected={onReposDetected} pollIntervalMs={50} />)

    await new Promise((r) => setTimeout(r, 150))

    expect(onReposDetected).not.toHaveBeenCalled()
  })

  it("renders the install link when mounted with the workspace already resolved", async () => {
    // How the app mounts it: Home only renders this screen once the workspace
    // is known, so isOwner is true on the first mount — and StrictMode then
    // mounts, tears down and remounts the effect.
    let mintCount = 0
    server.use(
      http.post("/installations/intents", () => {
        mintCount += 1
        return HttpResponse.json({
          install_url: `https://github.com/apps/test-app/installations/new?state=nonce-${mintCount}`,
        })
      })
    )

    renderWithProviders(
      <StrictMode>
        <WhenWorkspaceReady>
          <OnboardingScreen onReposDetected={vi.fn()} />
        </WhenWorkspaceReady>
      </StrictMode>
    )

    const installLink = await screen.findByRole("link", { name: /Install GitHub App/ })
    expect(installLink).toHaveAttribute(
      "href",
      "https://github.com/apps/test-app/installations/new?state=nonce-1"
    )
    expect(mintCount).toBe(1)
  })
})
