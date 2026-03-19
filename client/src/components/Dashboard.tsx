import { useState } from "react";
import { useRepos } from "@/hooks/useRepos";
import { useDashboard } from "@/hooks/useDashboard";
import { DashboardControls } from "@/components/DashboardControls";
import { MetricCard } from "@/components/MetricCard";
import { ChartPanel } from "@/components/ChartPanel";
import { DeploymentChart } from "@/components/charts/DeploymentChart";
import { LeadTimeChart } from "@/components/charts/LeadTimeChart";
import { CycleTimeChart } from "@/components/charts/CycleTimeChart";
import { PRAgeingChart } from "@/components/charts/PRAgeingChart";
import { Button } from "@/components/ui/button";
import type { DaysWindow } from "@/types/dashboard";

function formatDuration(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round((seconds / 3600) * 10) / 10}h`;
}

function timeAgo(isoString: string | null): string {
  if (!isoString) return "never";
  const diff = Date.now() - new Date(isoString).getTime();
  if (diff < 0) return "just now";
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function Dashboard() {
  const { repos, loading: reposLoading, error: reposError } = useRepos();
  const [userSelectedRepoId, setUserSelectedRepoId] = useState<string | null>(null);
  const [daysWindow, setDaysWindow] = useState<DaysWindow>(90);

  const selectedRepoId = userSelectedRepoId ?? (repos.length > 0 ? repos[0].id : null);
  const selectedRepo = repos.find((r) => r.id === selectedRepoId);
  const { data, loading, error, retry } = useDashboard(selectedRepoId, daysWindow);

  if (!reposLoading && !reposError && repos.length === 0) {
    return (
      <main className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">No repositories found</p>
      </main>
    );
  }

  const depFreq = data?.deployment_frequency;
  const leadTime = data?.lead_time;
  const cycleTime = data?.pr_cycle_time;
  const throughput = data?.throughput;
  const openPrs = data?.open_prs;
  const freshness = data?.data_quality?.freshness;

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
        <DashboardControls
          repos={repos}
          selectedRepoId={selectedRepoId}
          onRepoChange={setUserSelectedRepoId}
          daysWindow={daysWindow}
          onDaysWindowChange={setDaysWindow}
        />
      </div>

      {reposError && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-md border border-error-border bg-error-surface p-4 text-sm text-error"
        >
          <span>{reposError}</span>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-md border border-error-border bg-error-surface p-4 text-sm text-error"
        >
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={retry}>
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
          value={depFreq?.deploys_per_week != null ? depFreq.deploys_per_week.toFixed(1) : "—"}
          caption="deploys / week"
          loading={loading}
          setupRequired={depFreq?.status === "setup_required"}
        />
        <MetricCard
          title="Lead Time"
          value={leadTime?.median_seconds != null ? formatDuration(leadTime.median_seconds) : "—"}
          caption="Median: merge to production"
          loading={loading}
          setupRequired={leadTime?.status === "setup_required"}
        />
        <MetricCard
          title="PR Cycle Time"
          value={cycleTime?.median_seconds != null ? formatDuration(cycleTime.median_seconds) : "—"}
          caption="Median: PR open to merge"
          loading={loading}
          setupRequired={cycleTime?.status === "setup_required"}
        />
        <MetricCard
          title="Throughput"
          value={
            throughput?.prs_per_engineer_per_month != null
              ? throughput.prs_per_engineer_per_month.toFixed(1)
              : "—"
          }
          caption="PRs / engineer / month"
          loading={loading}
        />
        <MetricCard
          title="Open PRs"
          value={openPrs ? String(openPrs.total) : "—"}
          caption={openPrs ? `${openPrs.live} live · ${openPrs.draft} draft` : "Open pull requests"}
          loading={loading}
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
          loading={loading}
          empty={depFreq?.status === "setup_required" || !depFreq?.daily_counts?.length}
          emptyMessage={
            depFreq?.status === "setup_required"
              ? "Connect a production environment to track deployments"
              : "No deployments in this period"
          }
        >
          {depFreq?.daily_counts && <DeploymentChart dailyCounts={depFreq.daily_counts} />}
        </ChartPanel>
        <ChartPanel
          title="Lead Time"
          caption="Median and 75th percentile by week (hours)"
          info="Time from first commit to production deploy, shown as median and 75th percentile (P75). Lower lead time means faster delivery and shorter feedback loops."
          loading={loading}
          empty={leadTime?.status === "setup_required" || !leadTime?.weekly?.length}
          emptyMessage={
            leadTime?.status === "setup_required"
              ? "Connect a production environment to track lead time"
              : "No lead time data for this period"
          }
        >
          {leadTime?.weekly && <LeadTimeChart weekly={leadTime.weekly} />}
        </ChartPanel>
        <ChartPanel
          title="PR Cycle Time"
          caption="Median and 75th percentile by week (hours)"
          info="Time from PR opened to merged, shown as median and 75th percentile (P75). High cycle time often indicates bottlenecks in the review process."
          loading={loading}
          empty={cycleTime?.status === "setup_required" || !cycleTime?.weekly?.length}
          emptyMessage={
            cycleTime?.status === "setup_required"
              ? "Connect a production environment to track cycle time"
              : "No cycle time data for this period"
          }
        >
          {cycleTime?.weekly && <CycleTimeChart weekly={cycleTime.weekly} />}
        </ChartPanel>
        <ChartPanel
          title="PR Ageing"
          caption="Age distribution of open PRs"
          info="Age distribution of currently open PRs. A healthy team keeps most PRs in the green bucket — older PRs signal review delays or blocked work."
          loading={loading}
          empty={!data?.pr_ageing?.buckets?.length}
          emptyMessage="No open pull requests"
        >
          {data?.pr_ageing && <PRAgeingChart buckets={data.pr_ageing.buckets} />}
        </ChartPanel>
      </div>
    </main>
  );
}
