import logging
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
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

logger = logging.getLogger(__name__)

RECOMPUTE_DAYS = 90
ALGORITHM_VERSION = 1


def _cutoff(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=RECOMPUTE_DAYS)


def _week_start(dt: datetime | date) -> date:
    """Return Monday of the week containing dt."""
    d = dt.date() if isinstance(dt, datetime) else dt
    return d - timedelta(days=d.weekday())


def _percentile_75(sorted_values: list[float]) -> float:
    """P75 using nearest-rank method."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = int(0.75 * (n - 1))
    return sorted_values[idx]


async def compute_deployment_frequency(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    cutoff = _cutoff()
    result = await session.execute(
        select(ProductionDeploymentEvent).where(
            ProductionDeploymentEvent.tenant_id == tenant_id,
            ProductionDeploymentEvent.repo_id == repo_id,
            ProductionDeploymentEvent.deployed_at >= cutoff,
        )
    )
    deployments = result.scalars().all()

    counts: Counter = Counter()
    for dep in deployments:
        counts[dep.deployed_at.date()] += 1

    for day, count in counts.items():
        stmt = insert(DeploymentDailyMetric).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo_id,
            date=day,
            deployment_count=count,
            algorithm_version=ALGORITHM_VERSION,
        ).on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "date"],
            set_={
                "deployment_count": count,
                "algorithm_version": ALGORITHM_VERSION,
            },
        )
        await session.execute(stmt)


async def compute_lead_time(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    default_branch: str,
    session: AsyncSession,
) -> None:
    cutoff = _cutoff()
    result = await session.execute(
        select(
            PullRequest.merged_at,
            ProductionDeploymentEvent.deployed_at,
            PullRequest.base_ref,
        )
        .join(
            DeploymentAttribution,
            DeploymentAttribution.pr_id == PullRequest.id,
        )
        .join(
            ProductionDeploymentEvent,
            ProductionDeploymentEvent.id == DeploymentAttribution.deployment_id,
        )
        .where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo_id,
            PullRequest.base_ref == default_branch,
            ProductionDeploymentEvent.deployed_at >= cutoff,
        )
    )
    rows = result.all()

    weekly: defaultdict[date, list[float]] = defaultdict(list)
    for row in rows:
        lead_seconds = (row.deployed_at - row.merged_at).total_seconds()
        if lead_seconds <= 0:
            continue
        week = _week_start(row.deployed_at)
        weekly[week].append(lead_seconds)

    for week, durations in weekly.items():
        durations.sort()
        stmt = insert(LeadTimeWeeklyMetric).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo_id,
            week_start=week,
            median_seconds=statistics.median(durations),
            p75_seconds=_percentile_75(durations),
            sample_size=len(durations),
            algorithm_version=ALGORITHM_VERSION,
        ).on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "week_start"],
            set_={
                "median_seconds": statistics.median(durations),
                "p75_seconds": _percentile_75(durations),
                "sample_size": len(durations),
                "algorithm_version": ALGORITHM_VERSION,
            },
        )
        await session.execute(stmt)


async def compute_pr_cycle_time(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    default_branch: str,
    session: AsyncSession,
) -> None:
    cutoff = _cutoff()
    result = await session.execute(
        select(PullRequest).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo_id,
            PullRequest.base_ref == default_branch,
            PullRequest.merged_at >= cutoff,
        )
    )
    prs = result.scalars().all()

    weekly: defaultdict[date, list[float]] = defaultdict(list)
    for pr in prs:
        cycle_seconds = (pr.merged_at - pr.opened_at).total_seconds()
        if cycle_seconds <= 0:
            continue
        week = _week_start(pr.merged_at)
        weekly[week].append(cycle_seconds)

    for week, durations in weekly.items():
        durations.sort()
        stmt = insert(PRCycleTimeWeeklyMetric).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo_id,
            week_start=week,
            median_seconds=statistics.median(durations),
            p75_seconds=_percentile_75(durations),
            sample_size=len(durations),
            algorithm_version=ALGORITHM_VERSION,
        ).on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "week_start"],
            set_={
                "median_seconds": statistics.median(durations),
                "p75_seconds": _percentile_75(durations),
                "sample_size": len(durations),
                "algorithm_version": ALGORITHM_VERSION,
            },
        )
        await session.execute(stmt)


async def compute_pr_throughput(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    default_branch: str,
    session: AsyncSession,
) -> None:
    cutoff = _cutoff()
    result = await session.execute(
        select(PullRequest).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo_id,
            PullRequest.base_ref == default_branch,
            PullRequest.merged_at >= cutoff,
        )
    )
    prs = result.scalars().all()

    weekly: Counter = Counter()
    for pr in prs:
        week = _week_start(pr.merged_at)
        weekly[week] += 1

    for week, count in weekly.items():
        stmt = insert(PRThroughputWeeklyMetric).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo_id,
            week_start=week,
            pr_count=count,
            algorithm_version=ALGORITHM_VERSION,
        ).on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "week_start"],
            set_={
                "pr_count": count,
                "algorithm_version": ALGORITHM_VERSION,
            },
        )
        await session.execute(stmt)
