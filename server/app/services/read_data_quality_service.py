import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_attribution import DeploymentAttribution
from app.models.metrics import MetricsRefreshLog
from app.models.pull_request import PullRequest
from app.models.repository import Repository

STALE_THRESHOLD = timedelta(hours=2)


@dataclass
class MetricsFreshness:
    status: str  # "ok" | "stale" | "no_data"
    last_refresh_at: datetime | None
    days_of_data: int


async def get_metrics_freshness(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> MetricsFreshness:
    current_time = now or datetime.now(UTC)
    days_of_data = await get_days_of_data(
        tenant_id, repo_id, session, now=current_time
    )

    result = await session.execute(
        select(func.max(MetricsRefreshLog.completed_at)).where(
            MetricsRefreshLog.tenant_id == tenant_id,
            MetricsRefreshLog.repo_id == repo_id,
            MetricsRefreshLog.status == "success",
        )
    )
    last = result.scalar_one_or_none()

    if last is None:
        return MetricsFreshness(
            status="no_data", last_refresh_at=None, days_of_data=days_of_data
        )

    age = current_time - last
    status = "stale" if age > STALE_THRESHOLD else "ok"
    return MetricsFreshness(
        status=status, last_refresh_at=last, days_of_data=days_of_data
    )


async def get_days_of_data(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    """How many days of delivery history we have actually collected for a repo.

    `opened_at` is GitHub's creation time, not our ingest time, and we ingest a
    PR on its first handled action — so a PR opened long before the repo was
    connected arrives carrying that older timestamp and makes the span look
    wider than anything we observed. Collection starts when the repo was
    connected, so the later of the two bounds is the honest answer.

    A repo removed and re-added keeps its original row, so a gap in the middle
    still counts as collected.
    """
    result = await session.execute(
        select(func.min(PullRequest.opened_at)).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo_id,
        )
    )
    oldest = result.scalar_one_or_none()

    if oldest is None:
        return 0

    # Repository.id is the primary key, so this matches at most one row.
    connected = await session.execute(
        select(Repository.created_at).where(
            Repository.tenant_id == tenant_id,
            Repository.id == repo_id,
        )
    )
    connected_at = connected.scalar_one_or_none()

    start = max(oldest, connected_at) if connected_at is not None else oldest
    span = (now or datetime.now(UTC)) - start
    return max(span.days, 0)


async def get_attribution_coverage(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    default_branch: str,
    session: AsyncSession,
    days: int = 30,
) -> float | None:
    since = datetime.now(UTC) - timedelta(days=days)

    merged_in_window = PullRequest.merged_on_branch(tenant_id, repo_id, default_branch, since=since)

    total_result = await session.execute(
        select(func.count()).select_from(
            select(PullRequest.id).where(merged_in_window).subquery()
        )
    )
    total = total_result.scalar_one()

    if total == 0:
        return None

    attributed_result = await session.execute(
        select(func.count()).select_from(
            select(PullRequest.id)
            .where(
                merged_in_window,
                PullRequest.id.in_(
                    select(DeploymentAttribution.pr_id).where(
                        DeploymentAttribution.tenant_id == tenant_id,
                    )
                ),
            )
            .subquery()
        )
    )
    attributed = attributed_result.scalar_one()

    return round((attributed / total) * 100, 1)
