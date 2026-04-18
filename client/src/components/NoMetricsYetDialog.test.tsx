import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { NoMetricsYetDialog } from "./NoMetricsYetDialog"

const STORAGE_KEY = "distilled:cold-start-dismissed:"

describe("NoMetricsYetDialog", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it("renders when last_refresh_at is null", () => {
    render(<NoMetricsYetDialog repoId="r1" lastRefreshAt={null} />)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("does not render when last_refresh_at has a value", () => {
    render(<NoMetricsYetDialog repoId="r1" lastRefreshAt={"2026-01-01T00:00:00Z"} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("does not render when lastRefreshAt is undefined (still loading)", () => {
    render(<NoMetricsYetDialog repoId="r1" lastRefreshAt={undefined} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("does not render when already dismissed for this repo", () => {
    localStorage.setItem(STORAGE_KEY + "r1", "1")
    render(<NoMetricsYetDialog repoId="r1" lastRefreshAt={null} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("writes dismissal to localStorage keyed by repoId when dismissed", async () => {
    render(<NoMetricsYetDialog repoId="r1" lastRefreshAt={null} />)
    await userEvent.click(screen.getByRole("button", { name: /got it/i }))
    expect(localStorage.getItem(STORAGE_KEY + "r1")).toBe("1")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("reopens when switching to an undismissed repo", () => {
    localStorage.setItem(STORAGE_KEY + "r1", "1")
    const { rerender } = render(<NoMetricsYetDialog repoId="r1" lastRefreshAt={null} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    rerender(<NoMetricsYetDialog repoId="r2" lastRefreshAt={null} />)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("stays closed when switching back to a dismissed repo", () => {
    localStorage.setItem(STORAGE_KEY + "r1", "1")
    const { rerender } = render(<NoMetricsYetDialog repoId="r2" lastRefreshAt={null} />)
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    rerender(<NoMetricsYetDialog repoId="r1" lastRefreshAt={null} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
