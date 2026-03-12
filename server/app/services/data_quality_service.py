import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_attribution import DeploymentAttribution
from app.models.metrics import MetricsRefreshLog
from app.models.pull_request import PullRequest
from app.services.environment_service import get_production_environments

STALE_THRESHOLD = timedelta(hours=2)


@dataclass
class MetricsFreshness:
    status: str  # "ok" | "stale" | "no_data"
    last_refresh_at: datetime | None


async def get_metrics_freshness(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> MetricsFreshness:
    result = await session.execute(
        select(func.max(MetricsRefreshLog.completed_at)).where(
            MetricsRefreshLog.tenant_id == tenant_id,
            MetricsRefreshLog.repo_id == repo_id,
            MetricsRefreshLog.status == "success",
        )
    )
    last = result.scalar_one_or_none()

    if last is None:
        return MetricsFreshness(status="no_data", last_refresh_at=None)

    age = (now or datetime.now(timezone.utc)) - last
    status = "stale" if age > STALE_THRESHOLD else "ok"
    return MetricsFreshness(status=status, last_refresh_at=last)


async def get_attribution_coverage(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    default_branch: str,
    session: AsyncSession,
    days: int = 30,
) -> float | None:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_result = await session.execute(
        select(func.count()).select_from(
            select(PullRequest.id).where(
                PullRequest.tenant_id == tenant_id,
                PullRequest.repo_id == repo_id,
                PullRequest.base_ref == default_branch,
                PullRequest.merged_at >= since,
            ).subquery()
        )
    )
    total = total_result.scalar_one()

    if total == 0:
        return None

    attributed_result = await session.execute(
        select(func.count()).select_from(
            select(PullRequest.id).where(
                PullRequest.tenant_id == tenant_id,
                PullRequest.repo_id == repo_id,
                PullRequest.base_ref == default_branch,
                PullRequest.merged_at >= since,
                PullRequest.id.in_(
                    select(DeploymentAttribution.pr_id).where(
                        DeploymentAttribution.tenant_id == tenant_id,
                    )
                ),
            ).subquery()
        )
    )
    attributed = attributed_result.scalar_one()

    return round((attributed / total) * 100, 1)
