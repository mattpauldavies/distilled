import { render, screen } from "@testing-library/react"
import { InitialisingScreen } from "./InitialisingScreen"

describe("InitialisingScreen", () => {
  it("renders an Initialising message", () => {
    render(<InitialisingScreen />)
    expect(screen.getByText(/Initialising/i)).toBeInTheDocument()
  })

  it("announces loading state to assistive tech", () => {
    render(<InitialisingScreen />)
    const status = screen.getByRole("status")
    expect(status).toHaveAttribute("aria-live", "polite")
  })
})
