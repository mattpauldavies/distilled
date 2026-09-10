import { describe, expect, it, beforeEach, vi } from "vitest"
import { screen, waitFor } from "@testing-library/react"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token", isSignedIn: true }),
}))

import { renderWithProviders } from "@/test/render"
import { ACTIVE_WORKSPACE_STORAGE_KEY, useWorkspaceContext } from "@/lib/workspaceContext"

function ActiveWorkspaceProbe() {
  const { activeWorkspace, loading } = useWorkspaceContext()
  if (loading) return <p>loading</p>
  return <p>active: {activeWorkspace?.id ?? "none"}</p>
}

describe("WorkspaceProvider storage migration", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("migrates the legacy activeTenantId key to the workspace key", async () => {
    window.localStorage.setItem("distilled.activeTenantId", "workspace-1")

    renderWithProviders(<ActiveWorkspaceProbe />)

    await waitFor(() => {
      expect(screen.getByText("active: workspace-1")).toBeInTheDocument()
    })
    expect(window.localStorage.getItem(ACTIVE_WORKSPACE_STORAGE_KEY)).toBe("workspace-1")
    expect(window.localStorage.getItem("distilled.activeTenantId")).toBeNull()
  })

  it("prefers the new key when both exist", async () => {
    window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, "workspace-1")
    window.localStorage.setItem("distilled.activeTenantId", "workspace-stale")

    renderWithProviders(<ActiveWorkspaceProbe />)

    await waitFor(() => {
      expect(screen.getByText("active: workspace-1")).toBeInTheDocument()
    })
  })
})
