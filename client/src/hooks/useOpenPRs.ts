import type { OpenPRsSection } from "@/types/dashboard"
import { useMetricSection } from "./useMetricSection"

export function useOpenPRs(repoId: string | null) {
  return useMetricSection<OpenPRsSection>(
    repoId ? "/metrics/open-prs" : null,
    repoId ? { repo_id: repoId } : undefined
  )
}
