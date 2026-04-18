import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ReposErrorScreen } from "./ReposErrorScreen"

describe("ReposErrorScreen", () => {
  it("renders the error message", () => {
    render(<ReposErrorScreen error="Failed to fetch repos: 500" onRetry={vi.fn()} />)
    expect(screen.getByText("Failed to fetch repos: 500")).toBeInTheDocument()
  })

  it("fires onRetry when retry is clicked", async () => {
    const onRetry = vi.fn()
    render(<ReposErrorScreen error="boom" onRetry={onRetry} />)
    await userEvent.click(screen.getByRole("button", { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
