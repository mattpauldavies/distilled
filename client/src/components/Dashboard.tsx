import { useState } from "react"
import { useClerk } from "@clerk/clerk-react"
import { useDeploymentFrequency } from "@/hooks/useDeploymentFrequency"
import { useLeadTime } from "@/hooks/useLeadTime"
import { usePRCycleTime } from "@/hooks/usePRCycleTime"
import { useThroughput } from "@/hooks/useThroughput"
import { useOpenPRs } from "@/hooks/useOpenPRs"
import { usePRAgeing } from "@/hooks/usePRAgeing"
import { useDataQuality } from "@/hooks/useDataQuality"
import { DashboardControls } from "@/components/DashboardControls"
import { MetricCard } from "@/components/MetricCard"
import { ChartPanel } from "@/components/ChartPanel"
import { DeploymentChart } from "@/components/charts/DeploymentChart"
import { LeadTimeChart } from "@/components/charts/LeadTimeChart"
import { CycleTimeChart } from "@/components/charts/CycleTimeChart"
import { PRAgeingChart } from "@/components/charts/PRAgeingChart"
import { NoMetricsYetDialog } from "@/components/NoMetricsYetDialog"
import { Button } from "@/components/ui/button"
import type { DaysWindow, Repo } from "@/types/dashboard"

function SignOutButton() {
  const { signOut } = useClerk()
  return (
    <Button variant="outline" size="sm" onClick={() => signOut()}>
      Sign out
    </Button>
  )
}

function formatDuration(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${Math.round((seconds / 3600) * 10) / 10}h`
}

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
}

export function Dashboard({ repos }: DashboardProps) {
  const [userSelectedRepoId, setUserSelectedRepoId] = useState<string | null>(null)
  const [daysWindow, setDaysWindow] = useState<DaysWindow>(90)

  const selectedRepoId = userSelectedRepoId ?? repos[0].id
  const selectedRepo = repos.find((r) => r.id === selectedRepoId)

  const depFreq = useDeploymentFrequency(selectedRepoId, daysWindow)
  const leadTime = useLeadTime(selectedRepoId, daysWindow)
  const cycleTime = usePRCycleTime(selectedRepoId, daysWindow)
  const throughput = useThroughput(selectedRepoId, daysWindow)
  const openPrs = useOpenPRs(selectedRepoId)
  const prAgeing = usePRAgeing(selectedRepoId)
  const dataQuality = useDataQuality(selectedRepoId, daysWindow)

  const sections = [depFreq, leadTime, cycleTime, throughput, openPrs, prAgeing, dataQuality]
  const allErrored = sections.every((s) => s.error !== null)
  const firstError = sections.find((s) => s.error)?.error ?? null

  const freshness = dataQuality.data?.freshness

  return (
    <main className="mx-auto max-w-7xl space-y-8 px-6 py-8">
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
          />
          <SignOutButton />
        </div>
      </div>

      {allErrored && firstError && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-md border border-error-border bg-error-surface p-4 text-sm text-error"
        >
          <span>{firstError}</span>
          <Button variant="outline" size="sm" onClick={() => sections.forEach((s) => s.retry())}>
            Retry
          </Button>
        </div>
      )}

      <div className="flex items-center gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-primary">
          Key Metrics
        </h2>
        <div className="h-px flex-1 bg-separator" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <MetricCard
          title="Deployment Frequency"
          value={
            depFreq.data?.deploys_per_week != null ? depFreq.data.deploys_per_week.toFixed(1) : "—"
          }
          caption="deploys / week"
          loading={depFreq.loading}
          setupRequired={depFreq.data?.status === "setup_required"}
        />
        <MetricCard
          title="Lead Time"
          value={
            leadTime.data?.median_seconds != null
              ? formatDuration(leadTime.data.median_seconds)
              : "—"
          }
          caption="Median: merge to production"
          loading={leadTime.loading}
          setupRequired={leadTime.data?.status === "setup_required"}
        />
        <MetricCard
          title="PR Cycle Time"
          value={
            cycleTime.data?.median_seconds != null
              ? formatDuration(cycleTime.data.median_seconds)
              : "—"
          }
          caption="Median: PR open to merge"
          loading={cycleTime.loading}
          setupRequired={cycleTime.data?.status === "setup_required"}
        />
        <MetricCard
          title="Throughput"
          value={
            throughput.data?.prs_per_engineer_per_month != null
              ? throughput.data.prs_per_engineer_per_month.toFixed(1)
              : "—"
          }
          caption="PRs / engineer / month"
          loading={throughput.loading}
        />
        <MetricCard
          title="Open PRs"
          value={openPrs.data ? String(openPrs.data.total) : "—"}
          caption={
            openPrs.data
              ? `${openPrs.data.live} live · ${openPrs.data.draft} draft`
              : "Open pull requests"
          }
          loading={openPrs.loading}
        />
      </div>

      <div className="flex items-center gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-primary">Trends</h2>
        <div className="h-px flex-1 bg-separator" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartPanel
          title="Deployments"
          caption="Deployments per day"
          info="The number of deployments to production per day. A core DORA metric — higher frequency means smaller, safer changes shipped more often."
          loading={depFreq.loading}
          empty={depFreq.data?.status === "setup_required" || !depFreq.data?.daily_counts?.length}
          emptyMessage={
            depFreq.data?.status === "setup_required"
              ? "Connect a production environment to track deployments"
              : "No deployments in this period"
          }
        >
          {depFreq.data?.daily_counts && (
            <DeploymentChart dailyCounts={depFreq.data.daily_counts} />
          )}
        </ChartPanel>
        <ChartPanel
          title="Lead Time"
          caption="Median and 75th percentile by week (hours)"
          info="Time from first commit to production deploy, shown as median and 75th percentile (P75). Lower lead time means faster delivery and shorter feedback loops."
          loading={leadTime.loading}
          empty={leadTime.data?.status === "setup_required" || !leadTime.data?.weekly?.length}
          emptyMessage={
            leadTime.data?.status === "setup_required"
              ? "Connect a production environment to track lead time"
              : "No lead time data for this period"
          }
        >
          {leadTime.data?.weekly && <LeadTimeChart weekly={leadTime.data.weekly} />}
        </ChartPanel>
        <ChartPanel
          title="PR Cycle Time"
          caption="Median and 75th percentile by week (hours)"
          info="Time from PR opened to merged, shown as median and 75th percentile (P75). High cycle time often indicates bottlenecks in the review process."
          loading={cycleTime.loading}
          empty={cycleTime.data?.status === "setup_required" || !cycleTime.data?.weekly?.length}
          emptyMessage={
            cycleTime.data?.status === "setup_required"
              ? "Connect a production environment to track cycle time"
              : "No cycle time data for this period"
          }
        >
          {cycleTime.data?.weekly && <CycleTimeChart weekly={cycleTime.data.weekly} />}
        </ChartPanel>
        <ChartPanel
          title="PR Ageing"
          caption="Age distribution of open PRs"
          info="Age distribution of currently open PRs. A healthy team keeps most PRs in the green bucket — older PRs signal review delays or blocked work."
          loading={prAgeing.loading}
          empty={!prAgeing.data?.buckets?.length}
          emptyMessage="No open pull requests"
        >
          {prAgeing.data && <PRAgeingChart buckets={prAgeing.data.buckets} />}
        </ChartPanel>
      </div>

      {selectedRepoId && (
        <NoMetricsYetDialog repoId={selectedRepoId} lastRefreshAt={freshness?.last_refresh_at} />
      )}
    </main>
  )
}
