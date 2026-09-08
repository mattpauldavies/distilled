import { MetricCard } from "@/components/MetricCard"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { OpenPRsSection } from "@/types/dashboard"

interface Props {
  section: MetricSection<OpenPRsSection>
}

export function OpenPRsCard({ section }: Props) {
  const { data, loading, error, retry } = section
  const value = data ? String(data.total) : "—"
  const caption = data ? `${data.live} live · ${data.draft} draft` : "Open pull requests"

  return (
    <MetricCard
      title="Open PRs"
      value={value}
      caption={caption}
      loading={loading}
      error={error}
      onRetry={retry}
    />
  )
}
