import { useState } from "react"
import { useDataQuality } from "@/hooks/useDataQuality"
import { DashboardControls } from "@/components/DashboardControls"
import { isWindowAvailable } from "@/lib/daysWindow"
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
import { SignOutButton } from "@/components/SignOutButton"
import { TenantSwitcher } from "@/components/TenantSwitcher"
import { Button } from "@/components/ui/button"
import { useTenantContext } from "@/lib/tenantContext"
import type { DaysWindow, Repo } from "@/types/dashboard"

function timeAgo(isoString: string | null): string {
  if (!isoString) return "never"
  const diff = Date.now() - new Date(isoString).getTime()
  if (diff < 0) return "just now"
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

interface DashboardProps {
  repos: Repo[]
  onOpenTeam?: () => void
}

export function Dashboard({ repos, onOpenTeam }: DashboardProps) {
  const { activeTenant } = useTenantContext()
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
        <div className="flex shrink-0 items-center gap-3">
          <DashboardControls
            repos={repos}
            selectedRepoId={selectedRepoId}
            onRepoChange={setUserSelectedRepoId}
            daysWindow={daysWindow}
            onDaysWindowChange={setDaysWindow}
            daysOfData={daysOfData}
          />
          <TenantSwitcher />
          {activeTenant?.role === "owner" && onOpenTeam ? (
            <Button variant="outline" size="sm" onClick={onOpenTeam}>
              Team
            </Button>
          ) : null}
          <SignOutButton />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-primary">
          Key Metrics
        </h2>
        <div className="h-px flex-1 bg-separator" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <DeploymentFrequencyCard repoId={selectedRepoId} daysWindow={daysWindow} />
        <LeadTimeCard repoId={selectedRepoId} daysWindow={daysWindow} />
        <PRCycleTimeCard repoId={selectedRepoId} daysWindow={daysWindow} />
        <ThroughputCard repoId={selectedRepoId} daysWindow={daysWindow} />
        <OpenPRsCard repoId={selectedRepoId} />
      </div>

      <div className="flex items-center gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-primary">Trends</h2>
        <div className="h-px flex-1 bg-separator" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DeploymentFrequencyChartPanel repoId={selectedRepoId} daysWindow={daysWindow} />
        <LeadTimeChartPanel repoId={selectedRepoId} daysWindow={daysWindow} />
        <PRCycleTimeChartPanel repoId={selectedRepoId} daysWindow={daysWindow} />
        <PRAgeingChartPanel repoId={selectedRepoId} />
      </div>

      {selectedRepoId && (
        <NoMetricsYetDialog repoId={selectedRepoId} lastRefreshAt={freshness?.last_refresh_at} />
      )}
    </main>
  )
}
