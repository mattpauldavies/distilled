import type { DaysWindow, ThroughputSection } from "@/types/dashboard"
import { useMetricSection } from "./useMetricSection"

export function useThroughput(repoId: string | null, window: DaysWindow) {
  return useMetricSection<ThroughputSection>(
    repoId ? "/metrics/throughput" : null,
    repoId ? { repo_id: repoId, window } : undefined
  )
}
