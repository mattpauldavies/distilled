import type { DataQuality, DaysWindow } from "@/types/dashboard"
import { useMetricSection } from "./useMetricSection"

export function useDataQuality(repoId: string | null, window: DaysWindow) {
  return useMetricSection<DataQuality>(
    repoId ? "/metrics/data-quality" : null,
    repoId ? { repo_id: repoId, window } : undefined
  )
}
