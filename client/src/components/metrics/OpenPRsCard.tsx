import { useOpenPRs } from "@/hooks/useOpenPRs"
import { MetricCard } from "@/components/MetricCard"

interface Props {
  repoId: string
}

export function OpenPRsCard({ repoId }: Props) {
  const { data, loading, error, retry } = useOpenPRs(repoId)
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
