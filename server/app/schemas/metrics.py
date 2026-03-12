from datetime import date, datetime
from enum import IntEnum

from pydantic import BaseModel


class DaysWindow(IntEnum):
    THIRTY = 30
    SIXTY = 60
    NINETY = 90


class DailyCount(BaseModel):
    date: date
    count: int


class DeploymentFrequencyResponse(BaseModel):
    status: str
    message: str | None = None
    total: int | None = None
    days: int | None = None
    daily_counts: list[DailyCount] | None = None


# Shared shape for lead time + cycle time weekly percentiles
class WeeklyPercentiles(BaseModel):
    week_start: date
    median_seconds: float
    p75_seconds: float
    sample_size: int


# Backwards compat alias for existing lead-time endpoint
WeeklyLeadTime = WeeklyPercentiles


class LeadTimeResponse(BaseModel):
    status: str
    message: str | None = None
    days: int | None = None
    coverage_percent: float | None = None
    weekly: list[WeeklyPercentiles] | None = None


class OpenPRsResponse(BaseModel):
    total: int
    live: int
    draft: int


class AgeBucket(BaseModel):
    bucket: str
    count: int


class PRAgeingResponse(BaseModel):
    buckets: list[AgeBucket]


class WeeklyThroughput(BaseModel):
    week_start: date
    pr_count: int


# --- Unified dashboard response types ---


class DeploymentFrequencySection(BaseModel):
    status: str
    total: int | None = None
    days: int | None = None
    daily_counts: list[DailyCount] | None = None


class LeadTimeSection(BaseModel):
    status: str
    weekly: list[WeeklyPercentiles] | None = None


class PRCycleTimeSection(BaseModel):
    status: str
    weekly: list[WeeklyPercentiles] | None = None


class ThroughputSection(BaseModel):
    weekly: list[WeeklyThroughput] | None = None


class ScheduledMetrics(BaseModel):
    deployment_frequency: DeploymentFrequencySection
    lead_time: LeadTimeSection
    pr_cycle_time: PRCycleTimeSection
    throughput: ThroughputSection


class OpenPRsSection(BaseModel):
    total: int
    live: int
    draft: int


class PRAgeingSection(BaseModel):
    buckets: list[AgeBucket]


class LiveMetrics(BaseModel):
    open_prs: OpenPRsSection
    pr_ageing: PRAgeingSection


class FreshnessInfo(BaseModel):
    status: str
    last_refresh_at: datetime | None


class SetupInfo(BaseModel):
    has_production_environment: bool
    production_environments: list[str]


class DataQuality(BaseModel):
    attribution_coverage_percent: float | None
    freshness: FreshnessInfo
    setup: SetupInfo


class UnifiedDashboardResponse(BaseModel):
    scheduled: ScheduledMetrics
    live: LiveMetrics
    data_quality: DataQuality
