import { describe, expect, it, vi } from "vitest"
import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { renderWithProviders } from "@/test/render"
import { makeRepo } from "@/test/factories"
import { DeploymentTrackingPage } from "@/components/settings/DeploymentTrackingPage"

vi.mock("@clerk/clerk-react", () => {
  const stableGetToken = async () => "test-clerk-token"
  return {
    useAuth: () => ({ getToken: stableGetToken, isSignedIn: true }),
  }
})

function useRepoHandlers() {
  server.use(
    http.get("/repos", () =>
      HttpResponse.json({
        items: [
          makeRepo({ deployment_source: "deployment" }),
          makeRepo({
            id: "repo-2",
            full_name: "org/sdk",
            deployment_source: "release",
          }),
        ],
        total: 2,
        offset: 0,
        limit: 100,
      })
    )
  )
}

function sourceControl(fullName: string) {
  return within(screen.getByRole("radiogroup", { name: new RegExp(fullName) }))
}

describe("DeploymentTrackingPage", () => {
  it("shows each repo with its current source selected", async () => {
    useRepoHandlers()

    renderWithProviders(<DeploymentTrackingPage onClose={() => {}} />)

    expect(await screen.findByText("org/my-repo")).toBeInTheDocument()
    expect(sourceControl("org/my-repo").getByRole("radio", { name: "Deployments" })).toBeChecked()
    expect(sourceControl("org/sdk").getByRole("radio", { name: "Releases" })).toBeChecked()
  })

  it("switches a repo to release tracking", async () => {
    useRepoHandlers()
    let patched: { url: string; body: unknown } | null = null
    server.use(
      http.patch("/repos/:id", async ({ request, params }) => {
        patched = { url: String(params.id), body: await request.json() }
        return HttpResponse.json(makeRepo({ deployment_source: "release" }))
      })
    )

    renderWithProviders(<DeploymentTrackingPage onClose={() => {}} />)
    await screen.findByText("org/my-repo")

    await userEvent.click(sourceControl("org/my-repo").getByRole("radio", { name: "Releases" }))

    await waitFor(() => expect(patched).not.toBeNull())
    expect(patched!.url).toBe("repo-1")
    expect(patched!.body).toEqual({ deployment_source: "release" })
    expect(sourceControl("org/my-repo").getByRole("radio", { name: "Releases" })).toBeChecked()
  })

  it("restores the previous source and explains when the save fails", async () => {
    useRepoHandlers()
    server.use(http.patch("/repos/:id", () => new HttpResponse(null, { status: 500 })))

    renderWithProviders(<DeploymentTrackingPage onClose={() => {}} />)
    await screen.findByText("org/my-repo")

    await userEvent.click(sourceControl("org/my-repo").getByRole("radio", { name: "Releases" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(/org\/my-repo/)
    await waitFor(() =>
      expect(sourceControl("org/my-repo").getByRole("radio", { name: "Deployments" })).toBeChecked()
    )
  })

  it("returns to the dashboard", async () => {
    useRepoHandlers()
    const onClose = vi.fn()

    renderWithProviders(<DeploymentTrackingPage onClose={onClose} />)
    await screen.findByText("org/my-repo")

    await userEvent.click(screen.getByRole("button", { name: "Back to dashboard" }))

    expect(onClose).toHaveBeenCalled()
  })
})
