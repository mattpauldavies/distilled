import type { DaysWindow, DeploymentFrequencySection } from "@/types/dashboard"
import { useMetricSection } from "./useMetricSection"

export function useDeploymentFrequency(repoId: string | null, window: DaysWindow) {
  return useMetricSection<DeploymentFrequencySection>(
    repoId ? "/metrics/deployment-frequency" : null,
    repoId ? { repo_id: repoId, window } : undefined
  )
}
