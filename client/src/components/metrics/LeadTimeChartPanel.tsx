import { useLeadTime } from "@/hooks/useLeadTime"
import { ChartPanel } from "@/components/ChartPanel"
import { LeadTimeChart } from "@/components/charts/LeadTimeChart"
import type { DaysWindow } from "@/types/dashboard"

interface Props {
  repoId: string
  daysWindow: DaysWindow
}

export function LeadTimeChartPanel({ repoId, daysWindow }: Props) {
  const { data, loading } = useLeadTime(repoId, daysWindow)
  const isSetupRequired = data?.status === "setup_required"

  return (
    <ChartPanel
      title="Lead Time"
      caption="Median and 75th percentile by week (hours)"
      info="Time from first commit to production deploy, shown as median and 75th percentile (P75). Lower lead time means faster delivery and shorter feedback loops."
      loading={loading}
      empty={isSetupRequired || !data?.weekly?.length}
      emptyMessage={
        isSetupRequired
          ? "Connect a production environment to track lead time"
          : "No lead time data for this period"
      }
    >
      {data?.weekly && <LeadTimeChart weekly={data.weekly} />}
    </ChartPanel>
  )
}
