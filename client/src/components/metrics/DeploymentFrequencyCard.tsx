import { MetricCard } from "@/components/MetricCard"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { DeploymentFrequencySection } from "@/types/dashboard"

interface Props {
  section: MetricSection<DeploymentFrequencySection>
}

export function DeploymentFrequencyCard({ section }: Props) {
  const { data, loading, error, retry } = section
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
