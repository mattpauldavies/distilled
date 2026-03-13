import { useState } from "react";
import { useRepos } from "@/hooks/useRepos";
import { useDashboard } from "@/hooks/useDashboard";
import { DashboardControls } from "@/components/DashboardControls";
import { MetricCard } from "@/components/MetricCard";
import { ChartPanel } from "@/components/ChartPanel";
import { DataQualityPanel } from "@/components/DataQualityPanel";
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

export function Dashboard() {
  const { repos, loading: reposLoading, error: reposError } = useRepos();
  const [userSelectedRepoId, setUserSelectedRepoId] = useState<string | null>(null);
  const [daysWindow, setDaysWindow] = useState<DaysWindow>(30);

  // Auto-select first repo if user hasn't picked one
  const selectedRepoId = userSelectedRepoId ?? (repos.length > 0 ? repos[0].id : null);
  const { data, loading, error, retry } = useDashboard(selectedRepoId, daysWindow);

  if (!reposLoading && !reposError && repos.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">No repositories found</p>
      </div>
    );
  }

  const depFreq = data?.deployment_frequency;
  const leadTime = data?.lead_time;
  const cycleTime = data?.pr_cycle_time;
  const throughput = data?.throughput;
  const openPrs = data?.open_prs;

  const lastLeadTime = leadTime?.weekly?.length
    ? leadTime.weekly[leadTime.weekly.length - 1]
    : null;
  const lastCycleTime = cycleTime?.weekly?.length
    ? cycleTime.weekly[cycleTime.weekly.length - 1]
    : null;
  const lastThroughput = throughput?.weekly?.length
    ? throughput.weekly[throughput.weekly.length - 1]
    : null;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <DashboardControls
          repos={repos}
          selectedRepoId={selectedRepoId}
          onRepoChange={setUserSelectedRepoId}
          daysWindow={daysWindow}
          onDaysWindowChange={setDaysWindow}
        />
      </div>

      {reposError && (
        <div className="flex items-center gap-3 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <span>{reposError}</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-3 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={retry}>
            Retry
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <MetricCard
          title="Deployment Frequency"
          value={depFreq?.total != null ? String(depFreq.total) : "—"}
          caption={`Deployments in the last ${daysWindow} days`}
          loading={loading}
          setupRequired={depFreq?.status === "setup_required"}
        />
        <MetricCard
          title="Lead Time"
          value={lastLeadTime ? formatDuration(lastLeadTime.median_seconds) : "—"}
          caption="Median time from merge to production"
          loading={loading}
          setupRequired={leadTime?.status === "setup_required"}
        />
        <MetricCard
          title="PR Cycle Time"
          value={lastCycleTime ? formatDuration(lastCycleTime.median_seconds) : "—"}
          caption="Median time from PR open to merge"
          loading={loading}
          setupRequired={cycleTime?.status === "setup_required"}
        />
        <MetricCard
          title="Throughput"
          value={lastThroughput ? String(lastThroughput.pr_count) : "—"}
          caption="PRs merged this week"
          loading={loading}
        />
        <MetricCard
          title="Open PRs"
          value={openPrs ? String(openPrs.total) : "—"}
          caption="Currently open pull requests"
          subLabel={openPrs ? `${openPrs.live} live · ${openPrs.draft} draft` : undefined}
          loading={loading}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartPanel
          title="Deployments"
          caption="Daily deployment count"
          loading={loading}
          empty={depFreq?.status === "setup_required" || !depFreq?.daily_counts?.length}
          emptyMessage={depFreq?.status === "setup_required" ? "No data — production environment required" : "No deployment data"}
        >
          {depFreq?.daily_counts && <DeploymentChart dailyCounts={depFreq.daily_counts} />}
        </ChartPanel>
        <ChartPanel
          title="Lead Time"
          caption="Weekly median and p75 (hours)"
          loading={loading}
          empty={leadTime?.status === "setup_required" || !leadTime?.weekly?.length}
          emptyMessage={leadTime?.status === "setup_required" ? "No data — production environment required" : "No lead time data"}
        >
          {leadTime?.weekly && <LeadTimeChart weekly={leadTime.weekly} />}
        </ChartPanel>
        <ChartPanel
          title="PR Cycle Time"
          caption="Weekly median and p75 (hours)"
          loading={loading}
          empty={cycleTime?.status === "setup_required" || !cycleTime?.weekly?.length}
          emptyMessage={cycleTime?.status === "setup_required" ? "No data — production environment required" : "No cycle time data"}
        >
          {cycleTime?.weekly && <CycleTimeChart weekly={cycleTime.weekly} />}
        </ChartPanel>
        <ChartPanel
          title="PR Ageing"
          caption="Age distribution of open PRs"
          loading={loading}
          empty={!data?.pr_ageing?.buckets?.length}
          emptyMessage="No open PRs"
        >
          {data?.pr_ageing && <PRAgeingChart buckets={data.pr_ageing.buckets} />}
        </ChartPanel>
      </div>

      {data?.data_quality && <DataQualityPanel data={data.data_quality} />}
    </div>
  );
}
