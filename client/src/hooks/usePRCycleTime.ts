import type { DaysWindow, PRCycleTimeSection } from "@/types/dashboard"
import { useMetricSection } from "./useMetricSection"

export function usePRCycleTime(repoId: string | null, window: DaysWindow) {
  return useMetricSection<PRCycleTimeSection>(
    repoId ? "/metrics/pr-cycle-time" : null,
    repoId ? { repo_id: repoId, window } : undefined
  )
}
