import { usePRAgeing } from "@/hooks/usePRAgeing"
import { ChartPanel } from "@/components/ChartPanel"
import { PRAgeingChart } from "@/components/charts/PRAgeingChart"

interface Props {
  repoId: string
}

export function PRAgeingChartPanel({ repoId }: Props) {
  const { data, loading } = usePRAgeing(repoId)

  return (
    <ChartPanel
      title="PR Ageing"
      caption="Age distribution of open PRs"
      info="Age distribution of currently open PRs. A healthy team keeps most PRs in the green bucket — older PRs signal review delays or blocked work."
      loading={loading}
      empty={!data?.buckets?.length}
      emptyMessage="No open pull requests"
    >
      {data && <PRAgeingChart buckets={data.buckets} />}
    </ChartPanel>
  )
}
