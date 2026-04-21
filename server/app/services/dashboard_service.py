import uuid

from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.data_quality_service import get_attribution_coverage, get_metrics_freshness
from app.services.environment_service import get_production_environments
from app.services.metrics_service import (
    get_deployment_frequency,
    get_lead_time_aggregate,
    get_lead_time_summary,
    get_pr_cycle_time_aggregate,
    get_pr_cycle_time_summary,
    get_pr_throughput,
    get_pr_throughput_summary,
)
from app.services.pull_request_service import get_open_pr_count, get_pr_ageing


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
