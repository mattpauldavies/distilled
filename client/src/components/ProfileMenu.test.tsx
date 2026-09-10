import { describe, expect, it, vi } from "vitest"
import { screen } from "@testing-library/react"
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
})
