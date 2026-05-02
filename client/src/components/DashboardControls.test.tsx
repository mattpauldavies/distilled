import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DashboardControls } from "./DashboardControls"
import { makeRepo } from "@/test/factories"

describe("DashboardControls", () => {
  const repos = [makeRepo(), makeRepo({ id: "repo-2", full_name: "org/other-repo" })]

  it("renders window toggle buttons", () => {
    render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={90}
        onDaysWindowChange={() => {}}
        daysOfData={365}
      />
    )
    expect(screen.getByText("30d")).toBeInTheDocument()
    expect(screen.getByText("90d")).toBeInTheDocument()
    expect(screen.getByText("6m")).toBeInTheDocument()
  })

  it("calls onDaysWindowChange when clicking a window button", async () => {
    const user = userEvent.setup()
    const onDaysWindowChange = vi.fn()

    render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={30}
        onDaysWindowChange={onDaysWindowChange}
        daysOfData={365}
      />
    )

    await user.click(screen.getByText("90d"))
    expect(onDaysWindowChange).toHaveBeenCalledWith(90)
  })

  it("renders repo names in the select", () => {
    const { container } = render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={30}
        onDaysWindowChange={() => {}}
        daysOfData={365}
      />
    )
    // Radix select renders the selected repo name in the trigger
    expect(container.textContent).toContain("org/my-repo")
  })

  it("disables 90d and 6m when only 30 days of data are available", () => {
    render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={30}
        onDaysWindowChange={() => {}}
        daysOfData={30}
      />
    )

    expect(screen.getByRole("button", { name: "30d" })).not.toBeDisabled()
    expect(screen.getByRole("button", { name: "90d" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "6m" })).toBeDisabled()
  })

  it("enables 30d and 90d when more than 30 days but not more than 90 are available", () => {
    render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={30}
        onDaysWindowChange={() => {}}
        daysOfData={60}
      />
    )

    expect(screen.getByRole("button", { name: "30d" })).not.toBeDisabled()
    expect(screen.getByRole("button", { name: "90d" })).not.toBeDisabled()
    expect(screen.getByRole("button", { name: "6m" })).toBeDisabled()
  })

  it("enables all windows when more than 90 days are available", () => {
    render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={30}
        onDaysWindowChange={() => {}}
        daysOfData={120}
      />
    )

    expect(screen.getByRole("button", { name: "30d" })).not.toBeDisabled()
    expect(screen.getByRole("button", { name: "90d" })).not.toBeDisabled()
    expect(screen.getByRole("button", { name: "6m" })).not.toBeDisabled()
  })

  it("shows a tooltip explaining why a disabled window is unavailable", async () => {
    const user = userEvent.setup()
    render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={30}
        onDaysWindowChange={() => {}}
        daysOfData={12}
      />
    )

    await user.hover(screen.getByRole("button", { name: "90d" }).parentElement!)

    const tooltip = await screen.findByRole("tooltip")
    expect(tooltip.textContent).toContain("Only 12 days of data available")
  })
})
