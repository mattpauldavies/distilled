from datetime import date, datetime
from enum import IntEnum

from pydantic import BaseModel


class DaysWindow(IntEnum):
    THIRTY = 30
    NINETY = 90
    SIX_MONTHS = 180


class DailyCount(BaseModel):
    date: date
    count: int


class WeeklyPercentiles(BaseModel):
    week_start: date
    median_seconds: float
    p75_seconds: float
    sample_size: int


class AgeBucket(BaseModel):
    bucket: str
    count: int


class WeeklyThroughput(BaseModel):
    week_start: date
    pr_count: int


class DeploymentFrequencySection(BaseModel):
    status: str
    total: int | None = None
    days: int | None = None
    daily_counts: list[DailyCount] | None = None
    deploys_per_week: float | None = None


class LeadTimeSection(BaseModel):
    status: str
    weekly: list[WeeklyPercentiles] | None = None
    median_seconds: float | None = None


class PRCycleTimeSection(BaseModel):
    status: str
    weekly: list[WeeklyPercentiles] | None = None
    median_seconds: float | None = None


class ThroughputSection(BaseModel):
    weekly: list[WeeklyThroughput] | None = None
    total_prs: int | None = None
    unique_authors: int | None = None
    prs_per_engineer_per_month: float | None = None


class OpenPRsSection(BaseModel):
    total: int
    live: int
    draft: int


class PRAgeingSection(BaseModel):
    buckets: list[AgeBucket]


class FreshnessInfo(BaseModel):
    status: str
    last_refresh_at: datetime | None
    days_of_data: int | None = None


class SetupInfo(BaseModel):
    has_production_environment: bool
    production_environments: list[str]


class DataQuality(BaseModel):
    attribution_coverage_percent: float | None
    freshness: FreshnessInfo
    setup: SetupInfo
