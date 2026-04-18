import type { DaysWindow, LeadTimeSection } from "@/types/dashboard"
import { useMetricSection } from "./useMetricSection"

export function useLeadTime(repoId: string | null, window: DaysWindow) {
  return useMetricSection<LeadTimeSection>(
    repoId ? "/metrics/lead-time" : null,
    repoId ? { repo_id: repoId, window } : undefined
  )
}
