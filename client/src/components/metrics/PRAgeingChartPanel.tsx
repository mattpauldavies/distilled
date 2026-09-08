import { ChartPanel } from "@/components/ChartPanel"
import { PRAgeingChart } from "@/components/charts/PRAgeingChart"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { PRAgeingSection } from "@/types/dashboard"

interface Props {
  section: MetricSection<PRAgeingSection>
}

export function PRAgeingChartPanel({ section }: Props) {
  const { data, loading, error, retry } = section

  return (
    <ChartPanel
      title="PR Ageing"
      caption="Age distribution of open PRs"
      info="Age distribution of currently open PRs. A healthy team keeps most PRs in the green bucket — older PRs signal review delays or blocked work."
      loading={loading}
      error={error}
      onRetry={retry}
      empty={!data?.buckets?.length}
      emptyMessage="No open pull requests"
    >
      {data && <PRAgeingChart buckets={data.buckets} />}
    </ChartPanel>
  )
}
