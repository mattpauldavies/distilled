import { describe, expect, it, beforeEach, vi } from "vitest"
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { renderWithProviders } from "@/test/render"
import { CreateWorkspaceModal } from "@/components/CreateWorkspaceModal"
import { ACTIVE_WORKSPACE_STORAGE_KEY } from "@/lib/workspaceContext"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token", isSignedIn: true }),
}))

describe("CreateWorkspaceModal", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("creates a workspace and makes it active", async () => {
    let requestBody: unknown = null
    server.use(
      http.post("/workspaces", async ({ request }) => {
        requestBody = await request.json()
        return HttpResponse.json(
          { id: "workspace-new", name: "Acme Engineering", role: "owner" },
          { status: 201 }
        )
      })
    )

    const onOpenChange = vi.fn()
    renderWithProviders(<CreateWorkspaceModal open onOpenChange={onOpenChange} />)

    await userEvent.type(screen.getByLabelText("Workspace name"), "Acme Engineering")
    await userEvent.click(screen.getByRole("button", { name: "Create workspace" }))

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
    expect(requestBody).toEqual({ name: "Acme Engineering" })
    expect(window.localStorage.getItem(ACTIVE_WORKSPACE_STORAGE_KEY)).toBe("workspace-new")
  })

  it("disables submit while the name is empty", async () => {
    renderWithProviders(<CreateWorkspaceModal open onOpenChange={() => {}} />)
    expect(screen.getByRole("button", { name: "Create workspace" })).toBeDisabled()
  })

  it("shows the server error when creation fails", async () => {
    server.use(
      http.post("/workspaces", () =>
        HttpResponse.json({ detail: "Workspace name cannot be blank" }, { status: 400 })
      )
    )

    renderWithProviders(<CreateWorkspaceModal open onOpenChange={() => {}} />)
    await userEvent.type(screen.getByLabelText("Workspace name"), "x")
    await userEvent.click(screen.getByRole("button", { name: "Create workspace" }))

    expect(await screen.findByText("Workspace name cannot be blank")).toBeInTheDocument()
  })
})
