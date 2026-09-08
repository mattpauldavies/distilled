"""Read side of the metrics pipeline.

Live queries over raw PR/deployment rows, reads over the pre-computed metric
tables maintained by batch_metrics_service, and the dashboard section
builders served by the /metrics routes. Each metric's full read path — SQL
through to response schema — lives in this module.
"""

import statistics
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_attribution import DeploymentAttribution
from app.models.deployment_event import ProductionDeploymentEvent
from app.models.metrics import (
    DeploymentDailyMetric,
    LeadTimeWeeklyMetric,
    PRCycleTimeWeeklyMetric,
    PRThroughputWeeklyMetric,
)
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.schemas.metrics import (
    AgeBucket,
    DailyCount,
    DataQuality,
    DeploymentFrequencySection,
    FreshnessInfo,
    LeadTimeSection,
    OpenPRsSection,
    PRAgeingSection,
    PRCycleTimeSection,
    SetupInfo,
    ThroughputSection,
    WeeklyPercentiles,
    WeeklyThroughput,
)
from app.services.environment_service import get_production_environments
from app.services.read_data_quality_service import get_attribution_coverage, get_metrics_freshness


def _ageing_bucket_expr() -> Any:
    """SQL CASE expression for PR age buckets. Single definition — no duplication."""
    now = func.now()
    age = now - PullRequest.opened_at
    return sa.case(
        (age < sa.text("interval '2 days'"), sa.literal("<2d")),
        (age < sa.text("interval '7 days'"), sa.literal("2-7d")),
        (age < sa.text("interval '14 days'"), sa.literal("7-14d")),
        else_=sa.literal(">14d"),
    ).label("bucket")


async def get_open_pr_count(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
) -> dict:
    result = await session.execute(
        select(
            func.count().label("total"),
            func.sum(func.cast(PullRequest.is_draft == False, sa.Integer)).label("live"),
            func.sum(func.cast(PullRequest.is_draft == True, sa.Integer)).label("draft"),
        ).where(PullRequest.open_on_branch(tenant_id, repo.id, repo.default_branch))
    )
    row = result.one()
    return {
        "total": row.total or 0,
        "live": row.live or 0,
        "draft": row.draft or 0,
    }


async def get_pr_ageing(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
) -> list[dict]:
    bucket_expr = _ageing_bucket_expr()

    result = await session.execute(
        select(
            bucket_expr,
            func.count().label("count"),
        )
        .where(
            PullRequest.open_on_branch(tenant_id, repo.id, repo.default_branch),
            PullRequest.is_draft.is_(False),
        )
        .group_by(sa.text("bucket"))
    )
    _order = {"<2d": 0, "2-7d": 1, "7-14d": 2, ">14d": 3}
    counts = {row.bucket: row.count for row in result.all()}
    return [{"bucket": bucket, "count": counts.get(bucket, 0)} for bucket in sorted(_order, key=_order.__getitem__)]


async def get_lead_time_aggregate(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int,
) -> dict:
    """Live headline median: merge to production deploy, over the window."""
    since = datetime.now(UTC) - timedelta(days=days)
    result = await session.execute(
        select(
            PullRequest.merged_at,
            ProductionDeploymentEvent.deployed_at,
        )
        .join(DeploymentAttribution, DeploymentAttribution.pr_id == PullRequest.id)
        .join(ProductionDeploymentEvent, ProductionDeploymentEvent.id == DeploymentAttribution.deployment_id)
        .where(
            PullRequest.merged_on_branch(tenant_id, repo.id, repo.default_branch),
            ProductionDeploymentEvent.deployed_at >= since,
        )
    )
    durations = [
        (row.deployed_at - row.merged_at).total_seconds()
        for row in result.all()
        if (row.deployed_at - row.merged_at).total_seconds() > 0
    ]
    return {
        "median_seconds": statistics.median(durations) if durations else None,
        "sample_size": len(durations),
    }


async def get_pr_cycle_time_aggregate(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int,
) -> dict:
    """Live headline median: PR opened to merged, over the window."""
    since = datetime.now(UTC) - timedelta(days=days)
    result = await session.execute(
        select(PullRequest).where(
            PullRequest.merged_on_branch(tenant_id, repo.id, repo.default_branch, since=since)
        )
    )
    durations = [
        (pr.merged_at - pr.opened_at).total_seconds()
        for pr in result.scalars().all()
        if pr.merged_at is not None and pr.opened_at is not None and (pr.merged_at - pr.opened_at).total_seconds() > 0
    ]
    return {
        "median_seconds": statistics.median(durations) if durations else None,
        "sample_size": len(durations),
    }


async def get_pr_throughput_summary(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int,
) -> dict:
    """Live summary: merged PR count and per-engineer rate over the window."""
    since = datetime.combine(date.today() - timedelta(days=days), datetime.min.time(), tzinfo=UTC)
    result = await session.execute(
        select(
            func.count(PullRequest.id).label("total_prs"),
            func.count(distinct(PullRequest.author_login)).label("unique_authors"),
        ).where(PullRequest.merged_on_branch(tenant_id, repo.id, repo.default_branch, since=since))
    )
    row = result.one()
    total_prs = row.total_prs
    unique_authors = row.unique_authors
    if unique_authors > 0 and days > 0:
        prs_per_engineer_per_month = round(total_prs / unique_authors / (days / 30), 1)
    else:
        prs_per_engineer_per_month = None
    return {
        "total_prs": total_prs,
        "unique_authors": unique_authors,
        "prs_per_engineer_per_month": prs_per_engineer_per_month,
    }


async def get_deployment_frequency(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int,
) -> dict:
    since = date.today() - timedelta(days=days)
    result = await session.execute(
        select(DeploymentDailyMetric)
        .where(
            DeploymentDailyMetric.tenant_id == tenant_id,
            DeploymentDailyMetric.repo_id == repo.id,
            DeploymentDailyMetric.date >= since,
        )
        .order_by(DeploymentDailyMetric.date.asc())
    )
    metrics = result.scalars().all()
    daily_counts: list[dict[str, object]] = [{"date": m.date, "count": m.deployment_count} for m in metrics]
    total = sum(m.deployment_count for m in metrics)
    deploys_per_week = round(total / (days / 7), 1) if days > 0 else 0.0
    return {"total": total, "daily_counts": daily_counts, "deploys_per_week": deploys_per_week}


async def get_lead_time_summary(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int,
) -> list[dict]:
    since = date.today() - timedelta(days=days)
    result = await session.execute(
        select(LeadTimeWeeklyMetric)
        .where(
            LeadTimeWeeklyMetric.tenant_id == tenant_id,
            LeadTimeWeeklyMetric.repo_id == repo.id,
            LeadTimeWeeklyMetric.week_start >= since,
        )
        .order_by(LeadTimeWeeklyMetric.week_start.asc())
    )
    return [
        {
            "week_start": m.week_start,
            "median_seconds": m.median_seconds,
            "p75_seconds": m.p75_seconds,
            "sample_size": m.sample_size,
        }
        for m in result.scalars().all()
    ]


async def get_pr_cycle_time_summary(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int,
) -> list[dict]:
    since = date.today() - timedelta(days=days)
    result = await session.execute(
        select(PRCycleTimeWeeklyMetric)
        .where(
            PRCycleTimeWeeklyMetric.tenant_id == tenant_id,
            PRCycleTimeWeeklyMetric.repo_id == repo.id,
            PRCycleTimeWeeklyMetric.week_start >= since,
        )
        .order_by(PRCycleTimeWeeklyMetric.week_start.asc())
    )
    return [
        {
            "week_start": m.week_start,
            "median_seconds": m.median_seconds,
            "p75_seconds": m.p75_seconds,
            "sample_size": m.sample_size,
        }
        for m in result.scalars().all()
    ]


async def get_pr_throughput(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int,
) -> list[dict]:
    since = date.today() - timedelta(days=days)
    result = await session.execute(
        select(PRThroughputWeeklyMetric)
        .where(
            PRThroughputWeeklyMetric.tenant_id == tenant_id,
            PRThroughputWeeklyMetric.repo_id == repo.id,
            PRThroughputWeeklyMetric.week_start >= since,
        )
        .order_by(PRThroughputWeeklyMetric.week_start.asc())
    )
    return [{"week_start": m.week_start, "pr_count": m.pr_count} for m in result.scalars().all()]


async def get_deployment_frequency_section(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int = 30,
) -> DeploymentFrequencySection:
    prod_envs = await get_production_environments(tenant_id, repo.id, session)
    if not prod_envs:
        return DeploymentFrequencySection(status="setup_required")

    result = await get_deployment_frequency(tenant_id, repo, session, days)
    return DeploymentFrequencySection(
        status="ok",
        total=result["total"],
        days=days,
        daily_counts=[DailyCount(**dc) for dc in result["daily_counts"]],
        deploys_per_week=result["deploys_per_week"],
    )


async def get_lead_time_section(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int = 30,
) -> LeadTimeSection:
    prod_envs = await get_production_environments(tenant_id, repo.id, session)
    if not prod_envs:
        return LeadTimeSection(status="setup_required")

    weekly = await get_lead_time_summary(tenant_id, repo, session, days)
    agg = await get_lead_time_aggregate(tenant_id, repo, session, days)
    return LeadTimeSection(
        status="ok",
        weekly=[WeeklyPercentiles(**w) for w in weekly],
        median_seconds=agg["median_seconds"],
    )


async def get_pr_cycle_time_section(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int = 30,
) -> PRCycleTimeSection:
    prod_envs = await get_production_environments(tenant_id, repo.id, session)
    if not prod_envs:
        return PRCycleTimeSection(status="setup_required")

    weekly = await get_pr_cycle_time_summary(tenant_id, repo, session, days)
    agg = await get_pr_cycle_time_aggregate(tenant_id, repo, session, days)
    return PRCycleTimeSection(
        status="ok",
        weekly=[WeeklyPercentiles(**w) for w in weekly],
        median_seconds=agg["median_seconds"],
    )


async def get_throughput_section(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int = 30,
) -> ThroughputSection:
    weekly = await get_pr_throughput(tenant_id, repo, session, days)
    summary = await get_pr_throughput_summary(tenant_id, repo, session, days)
    return ThroughputSection(
        weekly=[WeeklyThroughput(**w) for w in weekly],
        total_prs=summary["total_prs"],
        unique_authors=summary["unique_authors"],
        prs_per_engineer_per_month=summary["prs_per_engineer_per_month"],
    )


async def get_open_prs_section(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
) -> OpenPRsSection:
    result = await get_open_pr_count(tenant_id, repo, session)
    return OpenPRsSection(**result)


async def get_pr_ageing_section(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
) -> PRAgeingSection:
    result = await get_pr_ageing(tenant_id, repo, session)
    return PRAgeingSection(buckets=[AgeBucket(**b) for b in result])


async def get_data_quality_section(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int = 30,
) -> DataQuality:
    prod_envs = await get_production_environments(tenant_id, repo.id, session)
    freshness = await get_metrics_freshness(tenant_id, repo.id, session)
    coverage = await get_attribution_coverage(
        tenant_id,
        repo.id,
        repo.default_branch,
        session,
        days,
    )
    return DataQuality(
        attribution_coverage_percent=coverage,
        freshness=FreshnessInfo(
            status=freshness.status,
            last_refresh_at=freshness.last_refresh_at,
            days_of_data=freshness.days_of_data,
        ),
        setup=SetupInfo(
            has_production_environment=len(prod_envs) > 0,
            production_environments=prod_envs,
        ),
    )
