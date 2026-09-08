import { MetricCard } from "@/components/MetricCard"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { ThroughputSection } from "@/types/dashboard"

interface Props {
  section: MetricSection<ThroughputSection>
}

export function ThroughputCard({ section }: Props) {
  const { data, loading, error, retry } = section
  const value =
    data?.prs_per_engineer_per_month != null ? data.prs_per_engineer_per_month.toFixed(1) : "—"

  return (
    <MetricCard
      title="Throughput"
      value={value}
      caption="PRs / engineer / month"
      loading={loading}
      error={error}
      onRetry={retry}
    />
  )
}
