import { ChartPanel } from "@/components/ChartPanel"
import { WeeklyPercentilesChart } from "@/components/charts/WeeklyPercentilesChart"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { LeadTimeSection } from "@/types/dashboard"

interface Props {
  section: MetricSection<LeadTimeSection>
}

export function LeadTimeChartPanel({ section }: Props) {
  const { data, loading, error, retry } = section
  const isSetupRequired = data?.status === "setup_required"

  return (
    <ChartPanel
      title="Lead Time"
      caption="Median and 75th percentile by week (hours)"
      info="Time from first commit to production deploy, shown as median and 75th percentile (P75). Lower lead time means faster delivery and shorter feedback loops."
      loading={loading}
      error={error}
      onRetry={retry}
      empty={isSetupRequired || !data?.weekly?.length}
      emptyMessage={
        isSetupRequired
          ? "Connect a production environment to track lead time"
          : "No lead time data for this period"
      }
    >
      {data?.weekly && (
        <WeeklyPercentilesChart
          weekly={data.weekly}
          ariaLabel="Line chart showing weekly lead time: median and 75th percentile in hours"
        />
      )}
    </ChartPanel>
  )
}
