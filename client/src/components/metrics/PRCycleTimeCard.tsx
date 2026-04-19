import { usePRCycleTime } from "@/hooks/usePRCycleTime"
import { MetricCard } from "@/components/MetricCard"
import { formatDuration } from "@/lib/format"
import type { DaysWindow } from "@/types/dashboard"

interface Props {
  repoId: string
  daysWindow: DaysWindow
}

export function PRCycleTimeCard({ repoId, daysWindow }: Props) {
  const { data, loading, error, retry } = usePRCycleTime(repoId, daysWindow)
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
