import { useState } from "react"
import { useDataQuality } from "@/hooks/useDataQuality"
import { useDeploymentFrequency } from "@/hooks/useDeploymentFrequency"
import { useLeadTime } from "@/hooks/useLeadTime"
import { useOpenPRs } from "@/hooks/useOpenPRs"
import { usePRAgeing } from "@/hooks/usePRAgeing"
import { usePRCycleTime } from "@/hooks/usePRCycleTime"
import { useThroughput } from "@/hooks/useThroughput"
import { DashboardControls } from "@/components/DashboardControls"
import { isWindowAvailable } from "@/lib/daysWindow"
import { timeAgo } from "@/lib/format"
import { DeploymentFrequencyCard } from "@/components/metrics/DeploymentFrequencyCard"
import { LeadTimeCard } from "@/components/metrics/LeadTimeCard"
import { PRCycleTimeCard } from "@/components/metrics/PRCycleTimeCard"
import { ThroughputCard } from "@/components/metrics/ThroughputCard"
import { OpenPRsCard } from "@/components/metrics/OpenPRsCard"
import { DeploymentFrequencyChartPanel } from "@/components/metrics/DeploymentFrequencyChartPanel"
import { LeadTimeChartPanel } from "@/components/metrics/LeadTimeChartPanel"
import { PRCycleTimeChartPanel } from "@/components/metrics/PRCycleTimeChartPanel"
import { PRAgeingChartPanel } from "@/components/metrics/PRAgeingChartPanel"
import { InvitationBanner } from "@/components/InvitationBanner"
import { NoMetricsYetDialog } from "@/components/NoMetricsYetDialog"
import type { DaysWindow, Repo } from "@/types/dashboard"

interface DashboardProps {
  repos: Repo[]
  onOpenTeam?: () => void
  onOpenRepos?: () => void
}

export function Dashboard({ repos, onOpenTeam, onOpenRepos }: DashboardProps) {
  const [userSelectedRepoId, setUserSelectedRepoId] = useState<string | null>(null)
  const [selectedDaysWindow, setDaysWindow] = useState<DaysWindow>(90)

  const selectedRepoId = userSelectedRepoId ?? repos[0].id
  const selectedRepo = repos.find((r) => r.id === selectedRepoId)

  const { data: dataQuality } = useDataQuality(selectedRepoId, selectedDaysWindow)
  const freshness = dataQuality?.freshness
  const daysOfData = freshness?.days_of_data ?? 0
  const daysWindow: DaysWindow = isWindowAvailable(selectedDaysWindow, daysOfData)
    ? selectedDaysWindow
    : 30

  const deploymentFrequency = useDeploymentFrequency(selectedRepoId, daysWindow)
  const leadTime = useLeadTime(selectedRepoId, daysWindow)
  const prCycleTime = usePRCycleTime(selectedRepoId, daysWindow)
  const throughput = useThroughput(selectedRepoId, daysWindow)
  const openPRs = useOpenPRs(selectedRepoId)
  const prAgeing = usePRAgeing(selectedRepoId)

  return (
    <main className="mx-auto max-w-7xl space-y-8 px-6 py-8">
      <InvitationBanner />
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1 pr-6">
          <h1 className="truncate text-2xl font-bold tracking-tight">
            {selectedRepo?.full_name ?? "Dashboard"}
          </h1>
          {freshness && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className={`size-1.5 rounded-full ${
                  freshness.status === "ok" ? "bg-success" : "bg-error"
                }`}
              />
              <span className="text-xs text-muted-foreground">
                {freshness.status === "ok" ? "Data current" : "Data stale"} · updated{" "}
                {timeAgo(freshness.last_refresh_at)}
                {daysOfData > 0 && (
                  <>
                    {" · "}
                    {daysOfData} {daysOfData === 1 ? "day" : "days"} of data
                  </>
                )}
              </span>
            </div>
          )}
        </div>
        <DashboardControls
          repos={repos}
          selectedRepoId={selectedRepoId}
          onRepoChange={setUserSelectedRepoId}
          daysWindow={daysWindow}
          onDaysWindowChange={setDaysWindow}
          daysOfData={daysOfData}
          onOpenTeam={onOpenTeam}
          onOpenRepos={onOpenRepos}
        />
      </div>

      <div className="flex items-center gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-primary">
          Key Metrics
        </h2>
        <div className="h-px flex-1 bg-separator" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <DeploymentFrequencyCard section={deploymentFrequency} />
        <LeadTimeCard section={leadTime} />
        <PRCycleTimeCard section={prCycleTime} />
        <ThroughputCard section={throughput} />
        <OpenPRsCard section={openPRs} />
      </div>

      <div className="flex items-center gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-primary">Trends</h2>
        <div className="h-px flex-1 bg-separator" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DeploymentFrequencyChartPanel section={deploymentFrequency} />
        <LeadTimeChartPanel section={leadTime} />
        <PRCycleTimeChartPanel section={prCycleTime} />
        <PRAgeingChartPanel section={prAgeing} />
      </div>

      {selectedRepoId && (
        <NoMetricsYetDialog repoId={selectedRepoId} lastRefreshAt={freshness?.last_refresh_at} />
      )}
    </main>
  )
}
