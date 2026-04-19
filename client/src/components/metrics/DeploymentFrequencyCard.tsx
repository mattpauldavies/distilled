import { useDeploymentFrequency } from "@/hooks/useDeploymentFrequency"
import { MetricCard } from "@/components/MetricCard"
import type { DaysWindow } from "@/types/dashboard"

interface Props {
  repoId: string
  daysWindow: DaysWindow
}

export function DeploymentFrequencyCard({ repoId, daysWindow }: Props) {
  const { data, loading, error, retry } = useDeploymentFrequency(repoId, daysWindow)
  const value = data?.deploys_per_week != null ? data.deploys_per_week.toFixed(1) : "—"

  return (
    <MetricCard
      title="Deployment Frequency"
      value={value}
      caption="deploys / week"
      loading={loading}
      error={error}
      onRetry={retry}
      setupRequired={data?.status === "setup_required"}
    />
  )
}
