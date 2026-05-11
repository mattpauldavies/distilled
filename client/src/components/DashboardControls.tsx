import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { DaysSelectorButton } from "@/components/DaysSelectorButton"
import { TenantSwitcher } from "@/components/TenantSwitcher"
import { WINDOWS } from "@/lib/daysWindow"
import type { Repo, DaysWindow } from "@/types/dashboard"

interface Props {
  repos: Repo[]
  selectedRepoId: string | null
  onRepoChange: (repoId: string) => void
  daysWindow: DaysWindow
  onDaysWindowChange: (daysWindow: DaysWindow) => void
  daysOfData: number
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
        {WINDOWS.map((w) => (
          <DaysSelectorButton
            key={w}
            window={w}
            selected={daysWindow}
            daysOfData={daysOfData}
            onSelect={onDaysWindowChange}
          />
        ))}
      </div>

      <TenantSwitcher />
    </div>
  )
}
