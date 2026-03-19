import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import type { Repo, DaysWindow } from "@/types/dashboard";

const WINDOWS: DaysWindow[] = [30, 90, 180];

const WINDOW_LABELS: Record<DaysWindow, string> = {
  30: "30d",
  90: "90d",
  180: "6m",
};

interface Props {
  repos: Repo[];
  selectedRepoId: string | null;
  onRepoChange: (repoId: string) => void;
  daysWindow: DaysWindow;
  onDaysWindowChange: (daysWindow: DaysWindow) => void;
}

export function DashboardControls({
  repos,
  selectedRepoId,
  onRepoChange,
  daysWindow,
  onDaysWindowChange,
}: Props) {
  return (
    <div className="flex items-center gap-4">
      <Select value={selectedRepoId ?? ""} onValueChange={onRepoChange}>
        <SelectTrigger className="w-[280px]">
          <SelectValue placeholder="Select a repository" />
        </SelectTrigger>
        <SelectContent>
          {repos.map((repo) => (
            <SelectItem key={repo.id} value={repo.id}>
              {repo.full_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div role="group" aria-label="Time window" className="flex rounded-md border border-border">
        {WINDOWS.map((w) => (
          <Button
            key={w}
            variant={w === daysWindow ? "default" : "ghost"}
            size="sm"
            aria-pressed={w === daysWindow}
            onClick={() => onDaysWindowChange(w)}
            className="rounded-none first:rounded-l-md last:rounded-r-md"
          >
            {WINDOW_LABELS[w]}
          </Button>
        ))}
      </div>
    </div>
  );
}
