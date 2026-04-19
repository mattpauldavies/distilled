import { usePRCycleTime } from "@/hooks/usePRCycleTime"
import { ChartPanel } from "@/components/ChartPanel"
import { CycleTimeChart } from "@/components/charts/CycleTimeChart"
import type { DaysWindow } from "@/types/dashboard"

interface Props {
  repoId: string
  daysWindow: DaysWindow
}

export function PRCycleTimeChartPanel({ repoId, daysWindow }: Props) {
  const { data, loading } = usePRCycleTime(repoId, daysWindow)
  const isSetupRequired = data?.status === "setup_required"

  return (
    <ChartPanel
      title="PR Cycle Time"
      caption="Median and 75th percentile by week (hours)"
      info="Time from PR opened to merged, shown as median and 75th percentile (P75). High cycle time often indicates bottlenecks in the review process."
      loading={loading}
      empty={isSetupRequired || !data?.weekly?.length}
      emptyMessage={
        isSetupRequired
          ? "Connect a production environment to track cycle time"
          : "No cycle time data for this period"
      }
    >
      {data?.weekly && <CycleTimeChart weekly={data.weekly} />}
    </ChartPanel>
  )
}
