import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import type { Repo, DaysWindow } from "@/types/dashboard";

const WINDOWS: DaysWindow[] = [7, 30, 90];

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

      <div className="flex rounded-md border border-border">
        {WINDOWS.map((w) => (
          <Button
            key={w}
            variant={w === daysWindow ? "default" : "ghost"}
            size="sm"
            onClick={() => onDaysWindowChange(w)}
            className="rounded-none first:rounded-l-md last:rounded-r-md"
          >
            {w}d
          </Button>
        ))}
      </div>
    </div>
  );
}
