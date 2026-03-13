import type {
  Repo,
  UnifiedDashboardResponse,
  DataQuality,
  DeploymentFrequencySection,
  LeadTimeSection,
  PRCycleTimeSection,
  ThroughputSection,
  OpenPRsSection,
  PRAgeingSection,
} from "@/types/dashboard";

export function makeRepo(overrides?: Partial<Repo>): Repo {
  return {
    id: "repo-1",
    github_id: 12345,
    full_name: "org/my-repo",
    default_branch: "main",
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

export function makeDeploymentFrequency(
  overrides?: Partial<DeploymentFrequencySection>
): DeploymentFrequencySection {
  return {
    status: "ok",
    total: 42,
    days: 30,
    daily_counts: [
      { date: "2025-06-01", count: 3 },
      { date: "2025-06-02", count: 5 },
    ],
    ...overrides,
  };
}

export function makeLeadTime(overrides?: Partial<LeadTimeSection>): LeadTimeSection {
  return {
    status: "ok",
    weekly: [
      { week_start: "2025-05-26", median_seconds: 7200, p75_seconds: 10800, sample_size: 10 },
    ],
    ...overrides,
  };
}

export function makeCycleTime(overrides?: Partial<PRCycleTimeSection>): PRCycleTimeSection {
  return {
    status: "ok",
    weekly: [
      { week_start: "2025-05-26", median_seconds: 3600, p75_seconds: 5400, sample_size: 8 },
    ],
    ...overrides,
  };
}

export function makeThroughput(overrides?: Partial<ThroughputSection>): ThroughputSection {
  return {
    weekly: [{ week_start: "2025-05-26", pr_count: 15 }],
    ...overrides,
  };
}

export function makeOpenPRs(overrides?: Partial<OpenPRsSection>): OpenPRsSection {
  return {
    total: 7,
    live: 5,
    draft: 2,
    ...overrides,
  };
}

export function makePRAgeing(overrides?: Partial<PRAgeingSection>): PRAgeingSection {
  return {
    buckets: [
      { bucket: "<1d", count: 3 },
      { bucket: "1-7d", count: 2 },
      { bucket: "7-30d", count: 1 },
      { bucket: ">30d", count: 1 },
    ],
    ...overrides,
  };
}

export function makeDataQuality(overrides?: Partial<DataQuality>): DataQuality {
  return {
    attribution_coverage_percent: 85.5,
    freshness: { status: "ok", last_refresh_at: new Date().toISOString() },
    setup: { has_production_environment: true, production_environments: ["production"] },
    ...overrides,
  };
}

export function makeDashboardResponse(
  overrides?: Partial<UnifiedDashboardResponse>
): UnifiedDashboardResponse {
  return {
    deployment_frequency: makeDeploymentFrequency(),
    lead_time: makeLeadTime(),
    pr_cycle_time: makeCycleTime(),
    throughput: makeThroughput(),
    open_prs: makeOpenPRs(),
    pr_ageing: makePRAgeing(),
    data_quality: makeDataQuality(),
    ...overrides,
  };
}
