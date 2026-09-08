import { ChartPanel } from "@/components/ChartPanel"
import { WeeklyPercentilesChart } from "@/components/charts/WeeklyPercentilesChart"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { PRCycleTimeSection } from "@/types/dashboard"

interface Props {
  section: MetricSection<PRCycleTimeSection>
}

export function PRCycleTimeChartPanel({ section }: Props) {
  const { data, loading, error, retry } = section
  const isSetupRequired = data?.status === "setup_required"

  return (
    <ChartPanel
      title="PR Cycle Time"
      caption="Median and 75th percentile by week (hours)"
      info="Time from PR opened to merged, shown as median and 75th percentile (P75). High cycle time often indicates bottlenecks in the review process."
      loading={loading}
      error={error}
      onRetry={retry}
      empty={isSetupRequired || !data?.weekly?.length}
      emptyMessage={
        isSetupRequired
          ? "Connect a production environment to track cycle time"
          : "No cycle time data for this period"
      }
    >
      {data?.weekly && (
        <WeeklyPercentilesChart
          weekly={data.weekly}
          ariaLabel="Line chart showing weekly PR cycle time: median and 75th percentile in hours"
        />
      )}
    </ChartPanel>
  )
}
