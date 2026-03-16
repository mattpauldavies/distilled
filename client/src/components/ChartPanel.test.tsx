import { render, screen } from "@testing-library/react";
import { ChartPanel } from "./ChartPanel";

describe("ChartPanel", () => {
  it("renders children when loaded", () => {
    render(
      <ChartPanel title="Deployments" caption="Daily count">
        <div data-testid="chart">chart content</div>
      </ChartPanel>
    );
    expect(screen.getByTestId("chart")).toBeInTheDocument();
    expect(screen.getByText("Deployments")).toBeInTheDocument();
  });

  it("shows skeleton when loading", () => {
    const { container } = render(
      <ChartPanel title="Deployments" caption="Daily count" loading>
        <div>chart</div>
      </ChartPanel>
    );
    expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument();
    expect(screen.queryByText("chart")).not.toBeInTheDocument();
  });

  it("shows empty message when empty", () => {
    render(
      <ChartPanel title="Deployments" caption="Daily count" empty emptyMessage="Nothing here">
        <div>chart</div>
      </ChartPanel>
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.queryByText("chart")).not.toBeInTheDocument();
  });

  it("renders InfoButton when info prop is provided", () => {
    render(
      <ChartPanel title="Deployments" caption="Daily count" info="Some info">
        <div>chart</div>
      </ChartPanel>
    );
    // aria-label="More information" on the InfoButton trigger — use regex for case-insensitive match
    expect(screen.getByRole("button", { name: /more information/i })).toBeInTheDocument();
  });

  it("does not render InfoButton when info prop is absent", () => {
    render(
      <ChartPanel title="Deployments" caption="Daily count">
        <div>chart</div>
      </ChartPanel>
    );
    expect(screen.queryByRole("button", { name: /more information/i })).not.toBeInTheDocument();
  });
});
