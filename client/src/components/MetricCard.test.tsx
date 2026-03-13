import { render, screen } from "@testing-library/react";
import { MetricCard } from "./MetricCard";

describe("MetricCard", () => {
  it("renders value and caption", () => {
    render(<MetricCard title="Deploys" value="42" caption="last 30 days" />);
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("last 30 days")).toBeInTheDocument();
    expect(screen.getByText("Deploys")).toBeInTheDocument();
  });

  it("shows skeleton when loading", () => {
    const { container } = render(
      <MetricCard title="Deploys" value="42" caption="last 30 days" loading />
    );
    expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument();
    expect(screen.queryByText("42")).not.toBeInTheDocument();
  });

  it("shows setup message when setupRequired", () => {
    render(
      <MetricCard title="Lead Time" value="—" caption="median" setupRequired />
    );
    expect(
      screen.getByText("Configure a production environment to see this metric")
    ).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });
});
