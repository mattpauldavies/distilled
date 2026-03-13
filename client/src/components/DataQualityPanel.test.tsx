import { render, screen } from "@testing-library/react";
import { DataQualityPanel } from "./DataQualityPanel";
import { makeDataQuality } from "@/test/factories";

describe("DataQualityPanel", () => {
  it("renders attribution coverage", () => {
    render(<DataQualityPanel data={makeDataQuality({ attribution_coverage_percent: 92.3 })} />);
    expect(screen.getByText("92.3%")).toBeInTheDocument();
  });

  it("shows fallback text when coverage is null", () => {
    render(<DataQualityPanel data={makeDataQuality({ attribution_coverage_percent: null })} />);
    expect(screen.getByText(/We're not sure what percentage/)).toBeInTheDocument();
  });

  it("renders freshness status", () => {
    render(
      <DataQualityPanel
        data={makeDataQuality({
          freshness: { status: "stale", last_refresh_at: "2025-01-01T00:00:00Z" },
        })}
      />
    );
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("shows production environment status", () => {
    render(
      <DataQualityPanel
        data={makeDataQuality({
          setup: {
            has_production_environment: false,
            production_environments: [],
          },
        })}
      />
    );
    expect(screen.getByText(/Deployments are not being tracked/)).toBeInTheDocument();
  });
});
