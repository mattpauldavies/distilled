import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { WINDOWS, WINDOW_LABELS, isWindowAvailable } from "@/lib/daysWindow"
import type { Repo, DaysWindow } from "@/types/dashboard"

interface Props {
  repos: Repo[]
  selectedRepoId: string | null
  onRepoChange: (repoId: string) => void
  daysWindow: DaysWindow
  onDaysWindowChange: (daysWindow: DaysWindow) => void
  daysOfData: number | null
}

export function DashboardControls({
  repos,
  selectedRepoId,
  onRepoChange,
  daysWindow,
  onDaysWindowChange,
  daysOfData,
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
        {WINDOWS.map((w) => {
          const available = isWindowAvailable(w, daysOfData)
          const button = (
            <Button
              variant={w === daysWindow ? "default" : "ghost"}
              size="sm"
              aria-pressed={w === daysWindow}
              disabled={!available}
              onClick={() => onDaysWindowChange(w)}
              className="rounded-none first:rounded-l-md last:rounded-r-md"
            >
              {WINDOW_LABELS[w]}
            </Button>
          )

          if (available) return <span key={w}>{button}</span>

          return (
            <Tooltip key={w}>
              <TooltipTrigger asChild>
                <span className="inline-flex cursor-not-allowed">{button}</span>
              </TooltipTrigger>
              <TooltipContent>
                Only {daysOfData} {daysOfData === 1 ? "day" : "days"} of data available — {w} days
                requires more history.
              </TooltipContent>
            </Tooltip>
          )
        })}
      </div>
    </div>
  )
}
