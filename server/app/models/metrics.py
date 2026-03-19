import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeploymentDailyMetric(Base):
    __tablename__ = "deployment_daily_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    date: Mapped[date] = mapped_column(Date)
    deployment_count: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)


class LeadTimeWeeklyMetric(Base):
    __tablename__ = "lead_time_weekly_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "week_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    week_start: Mapped[date] = mapped_column(Date)
    median_seconds: Mapped[float] = mapped_column(Float)
    p75_seconds: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)


class PRCycleTimeWeeklyMetric(Base):
    __tablename__ = "pr_cycle_time_weekly_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "week_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    week_start: Mapped[date] = mapped_column(Date)
    median_seconds: Mapped[float] = mapped_column(Float)
    p75_seconds: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)


class PRThroughputWeeklyMetric(Base):
    __tablename__ = "pr_throughput_weekly_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "week_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    week_start: Mapped[date] = mapped_column(Date)
    pr_count: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)


class MetricsRefreshLog(Base):
    __tablename__ = "metrics_refresh_log"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "hour"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
