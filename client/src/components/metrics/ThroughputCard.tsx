import { useThroughput } from "@/hooks/useThroughput"
import { MetricCard } from "@/components/MetricCard"
import type { DaysWindow } from "@/types/dashboard"

interface Props {
  repoId: string
  daysWindow: DaysWindow
}

export function ThroughputCard({ repoId, daysWindow }: Props) {
  const { data, loading, error, retry } = useThroughput(repoId, daysWindow)
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
