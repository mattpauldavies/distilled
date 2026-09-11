import { describe, expect, it, beforeEach, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { GitHubSetupPage } from "@/pages/GitHubSetupPage"
import { ACTIVE_WORKSPACE_STORAGE_KEY } from "@/lib/workspaceContext"

const authState = { isSignedIn: true, isLoaded: true }
const stableGetToken = async () => "test-clerk-token"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({
    ...authState,
    getToken: stableGetToken,
  }),
  SignIn: ({ redirectUrl }: { redirectUrl: string }) => (
    <div data-testid="clerk-sign-in" data-redirect-url={redirectUrl} />
  ),
}))

describe("GitHubSetupPage", () => {
  beforeEach(() => {
    window.localStorage.clear()
    authState.isSignedIn = true
    authState.isLoaded = true
  })

  it("shows sign-in with a redirect back when signed out", () => {
    authState.isSignedIn = false

    render(<GitHubSetupPage installationId={42} state="nonce-1" />)

    const signIn = screen.getByTestId("clerk-sign-in")
    expect(signIn.getAttribute("data-redirect-url")).toContain("/github/setup")
    expect(signIn.getAttribute("data-redirect-url")).toContain("state=nonce-1")
  })

  it("claims the installation and activates the bound workspace", async () => {
    let requestBody: unknown = null
    server.use(
      http.post("/installations/claim", async ({ request }) => {
        requestBody = await request.json()
        return HttpResponse.json({
          workspace_id: "workspace-9",
          workspace_name: "Acme Engineering",
        })
      })
    )
    const replace = vi.fn()
    vi.stubGlobal("location", { ...window.location, replace })

    render(<GitHubSetupPage installationId={42} state="nonce-1" />)

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/")
    })
    expect(requestBody).toEqual({ installation_id: 42, state: "nonce-1" })
    expect(window.localStorage.getItem(ACTIVE_WORKSPACE_STORAGE_KEY)).toBe("workspace-9")

    vi.unstubAllGlobals()
  })

  it("renders the error state with guidance when the claim fails", async () => {
    server.use(
      http.post("/installations/claim", () =>
        HttpResponse.json({ detail: "This installation link has expired" }, { status: 400 })
      )
    )

    render(<GitHubSetupPage installationId={42} state="stale" />)

    expect(await screen.findByText(/This installation link has expired/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Go to dashboard" })).toBeInTheDocument()
  })
})
