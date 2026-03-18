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
    UnifiedDashboardResponse,
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


async def get_unified_dashboard(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int = 30,
) -> UnifiedDashboardResponse:
    prod_envs = await get_production_environments(tenant_id, repo.id, session)
    has_prod = len(prod_envs) > 0

    if has_prod:
        dep_freq = await get_deployment_frequency(tenant_id, repo, session, days)
        lead_time = await get_lead_time_summary(tenant_id, repo, session, days)
        lead_time_agg = await get_lead_time_aggregate(tenant_id, repo, session, days)
        cycle_time = await get_pr_cycle_time_summary(tenant_id, repo, session, days)
        cycle_time_agg = await get_pr_cycle_time_aggregate(tenant_id, repo, session, days)
    else:
        dep_freq = lead_time = lead_time_agg = cycle_time = cycle_time_agg = None

    throughput = await get_pr_throughput(tenant_id, repo, session, days)
    throughput_summary = await get_pr_throughput_summary(tenant_id, repo, session, days)
    open_prs = await get_open_pr_count(tenant_id, repo, session)
    ageing = await get_pr_ageing(tenant_id, repo, session)
    freshness = await get_metrics_freshness(tenant_id, repo.id, session)
    coverage = await get_attribution_coverage(
        tenant_id, repo.id, repo.default_branch, session, days,
    )

    return UnifiedDashboardResponse(
        deployment_frequency=DeploymentFrequencySection(
            status="ok" if has_prod else "setup_required",
            total=dep_freq["total"] if dep_freq else None,
            days=days if dep_freq else None,
            daily_counts=[DailyCount(**dc) for dc in dep_freq["daily_counts"]] if dep_freq else None,
            deploys_per_week=dep_freq["deploys_per_week"] if dep_freq else None,
        ),
        lead_time=LeadTimeSection(
            status="ok" if has_prod else "setup_required",
            weekly=[WeeklyPercentiles(**w) for w in lead_time] if lead_time else None,
            median_seconds=lead_time_agg["median_seconds"] if lead_time_agg else None,
        ),
        pr_cycle_time=PRCycleTimeSection(
            status="ok" if has_prod else "setup_required",
            weekly=[WeeklyPercentiles(**w) for w in cycle_time] if cycle_time else None,
            median_seconds=cycle_time_agg["median_seconds"] if cycle_time_agg else None,
        ),
        throughput=ThroughputSection(
            weekly=[WeeklyThroughput(**w) for w in throughput],
            total_prs=throughput_summary["total_prs"],
            unique_authors=throughput_summary["unique_authors"],
            prs_per_engineer_per_month=throughput_summary["prs_per_engineer_per_month"],
        ),
        open_prs=OpenPRsSection(**open_prs),
        pr_ageing=PRAgeingSection(
            buckets=[AgeBucket(**b) for b in ageing],
        ),
        data_quality=DataQuality(
            attribution_coverage_percent=coverage,
            freshness=FreshnessInfo(
                status=freshness.status,
                last_refresh_at=freshness.last_refresh_at,
            ),
            setup=SetupInfo(
                has_production_environment=has_prod,
                production_environments=prod_envs,
            ),
        ),
    )
