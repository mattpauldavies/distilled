import { MetricCard } from "@/components/MetricCard"
import { formatDuration } from "@/lib/format"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { LeadTimeSection } from "@/types/dashboard"

interface Props {
  section: MetricSection<LeadTimeSection>
}

export function LeadTimeCard({ section }: Props) {
  const { data, loading, error, retry } = section
  const value = data?.median_seconds != null ? formatDuration(data.median_seconds) : "—"

  return (
    <MetricCard
      title="Lead Time"
      value={value}
      caption="Median: merge to production"
      loading={loading}
      error={error}
      onRetry={retry}
      setupRequired={data?.status === "setup_required"}
    />
  )
}
