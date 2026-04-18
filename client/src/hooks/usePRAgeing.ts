import type { PRAgeingSection } from "@/types/dashboard"
import { useMetricSection } from "./useMetricSection"

export function usePRAgeing(repoId: string | null) {
  return useMetricSection<PRAgeingSection>(
    repoId ? "/metrics/pr-ageing" : null,
    repoId ? { repo_id: repoId } : undefined
  )
}
