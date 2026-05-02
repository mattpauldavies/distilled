export interface DailyCount {
  date: string
  count: number
}

export interface WeeklyPercentiles {
  week_start: string
  median_seconds: number
  p75_seconds: number
  sample_size: number
}

export interface WeeklyThroughput {
  week_start: string
  pr_count: number
}

export interface AgeBucket {
  bucket: string
  count: number
}

export interface DeploymentFrequencySection {
  status: string
  total: number | null
  days: number | null
  daily_counts: DailyCount[] | null
  deploys_per_week: number | null
}

export interface LeadTimeSection {
  status: string
  weekly: WeeklyPercentiles[] | null
  median_seconds: number | null
}

export interface PRCycleTimeSection {
  status: string
  weekly: WeeklyPercentiles[] | null
  median_seconds: number | null
}

export interface ThroughputSection {
  weekly: WeeklyThroughput[] | null
  total_prs: number | null
  unique_authors: number | null
  prs_per_engineer_per_month: number | null
}

export interface OpenPRsSection {
  total: number
  live: number
  draft: number
}

export interface PRAgeingSection {
  buckets: AgeBucket[]
}

export interface FreshnessInfo {
  status: string
  last_refresh_at: string | null
  days_of_data: number
}

export interface SetupInfo {
  has_production_environment: boolean
  production_environments: string[]
}

export interface DataQuality {
  attribution_coverage_percent: number | null
  freshness: FreshnessInfo
  setup: SetupInfo
}

export interface Repo {
  id: string
  github_id: number
  full_name: string
  default_branch: string
  created_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}

export type DaysWindow = 30 | 90 | 180
