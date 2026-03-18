import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DashboardControls } from "./DashboardControls";
import { makeRepo } from "@/test/factories";

describe("DashboardControls", () => {
  const repos = [makeRepo(), makeRepo({ id: "repo-2", full_name: "org/other-repo" })];

  it("renders window toggle buttons", () => {
    render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={90}
        onDaysWindowChange={() => {}}
      />
    );
    expect(screen.getByText("30d")).toBeInTheDocument();
    expect(screen.getByText("90d")).toBeInTheDocument();
    expect(screen.getByText("6m")).toBeInTheDocument();
  });

  it("calls onDaysWindowChange when clicking a window button", async () => {
    const user = userEvent.setup();
    const onDaysWindowChange = vi.fn();

    render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={90}
        onDaysWindowChange={onDaysWindowChange}
      />
    );

    await user.click(screen.getByText("6m"));
    expect(onDaysWindowChange).toHaveBeenCalledWith(180);
  });

  it("renders repo names in the select", () => {
    const { container } = render(
      <DashboardControls
        repos={repos}
        selectedRepoId="repo-1"
        onRepoChange={() => {}}
        daysWindow={30}
        onDaysWindowChange={() => {}}
      />
    );
    // Radix select renders the selected repo name in the trigger
    expect(container.textContent).toContain("org/my-repo");
  });
});
