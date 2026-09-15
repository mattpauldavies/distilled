import { describe, expect, it, vi } from "vitest"
import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { renderWithProviders } from "@/test/render"
import { ProfileMenu } from "@/components/ProfileMenu"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token", isSignedIn: true }),
  useUser: () => ({ user: { fullName: "Test User", imageUrl: null } }),
  useClerk: () => ({ signOut: vi.fn() }),
}))

describe("ProfileMenu", () => {
  it("offers Create workspace beneath the membership list", async () => {
    renderWithProviders(<ProfileMenu />)

    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }))
    expect(await screen.findByText("Test Workspace")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /Create workspace/ }))
    expect(await screen.findByText("Create a workspace")).toBeInTheDocument()
  })

  it("offers Deployment Tracking to owners", async () => {
    const onOpenDeploymentTracking = vi.fn()
    renderWithProviders(<ProfileMenu onOpenDeploymentTracking={onOpenDeploymentTracking} />)

    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }))
    await userEvent.click(await screen.findByRole("button", { name: "Deployment Tracking" }))

    expect(onOpenDeploymentTracking).toHaveBeenCalled()
  })

  it("groups the settings entries under a Settings heading", async () => {
    renderWithProviders(
      <ProfileMenu onOpenTeam={vi.fn()} onOpenRepos={vi.fn()} onOpenDeploymentTracking={vi.fn()} />
    )

    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }))

    const settings = await screen.findByRole("group", { name: "Settings" })
    expect(within(settings).getByRole("button", { name: "Team" })).toBeInTheDocument()
    expect(within(settings).getByRole("button", { name: "Repositories" })).toBeInTheDocument()
    expect(
      within(settings).getByRole("button", { name: "Deployment Tracking" })
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Team Settings" })).not.toBeInTheDocument()
  })
})
