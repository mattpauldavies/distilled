import { useLeadTime } from "@/hooks/useLeadTime"
import { MetricCard } from "@/components/MetricCard"
import { formatDuration } from "@/lib/format"
import type { DaysWindow } from "@/types/dashboard"

interface Props {
  repoId: string
  daysWindow: DaysWindow
}

export function LeadTimeCard({ repoId, daysWindow }: Props) {
  const { data, loading, error, retry } = useLeadTime(repoId, daysWindow)
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
