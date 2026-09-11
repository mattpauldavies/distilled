import { describe, expect, it, vi } from "vitest"
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { renderWithProviders } from "@/test/render"
import { RepositoriesPage } from "@/components/repos/RepositoriesPage"

vi.mock("@clerk/clerk-react", () => {
  const stableGetToken = async () => "test-clerk-token"
  return {
    useAuth: () => ({ getToken: stableGetToken, isSignedIn: true }),
  }
})

function useInstallationHandlers() {
  server.use(
    http.get("/installations", () =>
      HttpResponse.json({
        items: [
          {
            installation_id: 42,
            account_login: "acme",
            account_type: "organization",
            repo_count: 2,
            removed: false,
          },
        ],
      })
    )
  )
}

describe("RepositoriesPage", () => {
  it("lists tracked repos and connected installations", async () => {
    useInstallationHandlers()

    renderWithProviders(<RepositoriesPage onClose={() => {}} />)

    expect(await screen.findByText("org/my-repo")).toBeInTheDocument()
    expect(await screen.findByText("acme")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Add repositories" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Connect GitHub/ })).toBeInTheDocument()
  })

  it("removes a repo after confirmation, noting history is retained", async () => {
    useInstallationHandlers()
    let deleted: string | null = null
    server.use(
      http.delete("/repos/:id", ({ params }) => {
        deleted = params.id as string
        return new HttpResponse(null, { status: 204 })
      })
    )

    renderWithProviders(<RepositoriesPage onClose={() => {}} />)

    const removeButtons = await screen.findAllByRole("button", { name: "Remove" })
    await userEvent.click(removeButtons[0])

    expect(await screen.findByText(/historical data is retained/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Remove repository" }))

    await waitFor(() => {
      expect(deleted).toBe("repo-1")
    })
  })

  it("unlinks an installation after confirmation", async () => {
    useInstallationHandlers()
    let unlinked = false
    server.use(
      http.delete("/installations/42", () => {
        unlinked = true
        return new HttpResponse(null, { status: 204 })
      })
    )

    renderWithProviders(<RepositoriesPage onClose={() => {}} />)

    await userEvent.click(await screen.findByRole("button", { name: "Unlink" }))
    await userEvent.click(await screen.findByRole("button", { name: "Unlink installation" }))

    await waitFor(() => {
      expect(unlinked).toBe(true)
    })
  })

  it("opens the add-repos picker with tracked repos disabled and posts the selection", async () => {
    useInstallationHandlers()
    server.use(
      http.get("/installations/42/available-repos", () =>
        HttpResponse.json({
          items: [
            { github_id: 101, full_name: "acme/api", default_branch: "main", tracked: true },
            { github_id: 102, full_name: "acme/web", default_branch: "main", tracked: false },
          ],
        })
      )
    )
    let requestBody: unknown = null
    server.use(
      http.post("/repos", async ({ request }) => {
        requestBody = await request.json()
        return HttpResponse.json([], { status: 201 })
      })
    )

    renderWithProviders(<RepositoriesPage onClose={() => {}} />)

    await userEvent.click(await screen.findByRole("button", { name: "Add repositories" }))

    const tracked = await screen.findByRole("checkbox", { name: /acme\/api/ })
    expect(tracked).toBeDisabled()

    await userEvent.click(screen.getByRole("checkbox", { name: /acme\/web/ }))
    await userEvent.click(screen.getByRole("button", { name: "Add selected" }))

    await waitFor(() => {
      expect(requestBody).toEqual({ installation_id: 42, github_ids: [102] })
    })
  })

  it("connects GitHub via a fresh installation intent", async () => {
    useInstallationHandlers()
    const assign = vi.fn()
    vi.stubGlobal("location", { ...window.location, assign })

    renderWithProviders(<RepositoriesPage onClose={() => {}} />)

    await userEvent.click(await screen.findByRole("button", { name: /Connect GitHub/ }))

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(
        "https://github.com/apps/test-app/installations/new?state=test-nonce"
      )
    })
    vi.unstubAllGlobals()
  })
})
