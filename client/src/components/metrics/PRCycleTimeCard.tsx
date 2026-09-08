import { MetricCard } from "@/components/MetricCard"
import { formatDuration } from "@/lib/format"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { PRCycleTimeSection } from "@/types/dashboard"

interface Props {
  section: MetricSection<PRCycleTimeSection>
}

export function PRCycleTimeCard({ section }: Props) {
  const { data, loading, error, retry } = section
  const value = data?.median_seconds != null ? formatDuration(data.median_seconds) : "—"

  return (
    <MetricCard
      title="PR Cycle Time"
      value={value}
      caption="Median: PR open to merge"
      loading={loading}
      error={error}
      onRetry={retry}
      setupRequired={data?.status === "setup_required"}
    />
  )
}
