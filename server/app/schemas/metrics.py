from datetime import date

from pydantic import BaseModel


class DailyCount(BaseModel):
    date: date
    count: int


class DeploymentFrequencyResponse(BaseModel):
    status: str
    message: str | None = None
    total: int | None = None
    days: int | None = None
    daily_counts: list[DailyCount] | None = None


class WeeklyLeadTime(BaseModel):
    week_start: date
    median_seconds: float
    p75_seconds: float
    sample_size: int


class LeadTimeResponse(BaseModel):
    status: str
    message: str | None = None
    days: int | None = None
    coverage_percent: float | None = None
    weekly: list[WeeklyLeadTime] | None = None
