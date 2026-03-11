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
