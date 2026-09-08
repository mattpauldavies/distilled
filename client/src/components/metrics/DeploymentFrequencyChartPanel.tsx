import { ChartPanel } from "@/components/ChartPanel"
import { DeploymentChart } from "@/components/charts/DeploymentChart"
import type { MetricSection } from "@/hooks/useMetricSection"
import type { DeploymentFrequencySection } from "@/types/dashboard"

interface Props {
  section: MetricSection<DeploymentFrequencySection>
}

export function DeploymentFrequencyChartPanel({ section }: Props) {
  const { data, loading, error, retry } = section
  const isSetupRequired = data?.status === "setup_required"

  return (
    <ChartPanel
      title="Deployments"
      caption="Deployments per day"
      info="The number of deployments to production per day. A core DORA metric — higher frequency means smaller, safer changes shipped more often."
      loading={loading}
      error={error}
      onRetry={retry}
      empty={isSetupRequired || !data?.daily_counts?.length}
      emptyMessage={
        isSetupRequired
          ? "Connect a production environment to track deployments"
          : "No deployments in this period"
      }
    >
      {data?.daily_counts && <DeploymentChart dailyCounts={data.daily_counts} />}
    </ChartPanel>
  )
}
