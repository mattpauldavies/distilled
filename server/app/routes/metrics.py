import uuid
from datetime import date, datetime, timedelta, timezone
from enum import IntEnum

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.middleware.repo import get_verified_repo
from app.middleware.tenant import get_tenant_id
from app.models.deployment_attribution import DeploymentAttribution
from app.models.environment import Environment
from app.models.metrics import DeploymentDailyMetric, LeadTimeWeeklyMetric, MetricsRefreshLog
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.schemas.metrics import (
    DailyCount, DeploymentFrequencyResponse, LeadTimeResponse, WeeklyLeadTime,
    OpenPRsResponse, AgeBucket, PRAgeingResponse,
)
from app.services.metrics_service import recompute_repo

router = APIRouter(prefix="/metrics")


class RecomputeRequest(BaseModel):
    tenant_id: uuid.UUID
    repo_id: uuid.UUID


_bearer_scheme = HTTPBearer()


def _verify_cron_secret(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    if not settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="cron secret not configured")
    if credentials.credentials != settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="invalid authorization")


@router.post("/recompute")
async def recompute_metrics(
    body: RecomputeRequest,
    _auth: None = Depends(_verify_cron_secret),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Look up repo for default_branch
    repo_result = await session.execute(
        select(Repository).where(
            Repository.id == body.repo_id,
            Repository.tenant_id == body.tenant_id,
        )
    )
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="repo not found")

    now = datetime.now(timezone.utc)
    hour = now.replace(minute=0, second=0, microsecond=0)

    result = await recompute_repo(
        body.tenant_id, body.repo_id, repo.default_branch, session,
    )

    # UPSERT refresh log (dedup per hour)
    stmt = insert(MetricsRefreshLog).values(
        id=uuid.uuid4(),
        tenant_id=body.tenant_id,
        repo_id=body.repo_id,
        hour=hour,
        started_at=now,
        completed_at=datetime.now(timezone.utc),
        status=result.status,
        error_message=result.error_message,
    ).on_conflict_do_update(
        index_elements=["tenant_id", "repo_id", "hour"],
        set_={
            "started_at": now,
            "completed_at": datetime.now(timezone.utc),
            "status": result.status,
            "error_message": result.error_message,
        },
    )
    await session.execute(stmt)
    await session.commit()

    return {"status": result.status, "error_message": result.error_message}


class DaysWindow(IntEnum):
    THIRTY = 30
    SIXTY = 60
    NINETY = 90


@router.get("/deployment-frequency")
async def get_deployment_frequency(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    days: DaysWindow = Query(DaysWindow.THIRTY),
) -> DeploymentFrequencyResponse:
    # Check for production environment
    env_result = await session.execute(
        select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.repo_id == repo.id,
            Environment.is_production.is_(True),
        ).limit(1)
    )
    if not env_result.scalar_one_or_none():
        return DeploymentFrequencyResponse(
            status="setup_required",
            message="no production environment configured",
        )

    since = date.today() - timedelta(days=int(days))
    result = await session.execute(
        select(DeploymentDailyMetric).where(
            DeploymentDailyMetric.tenant_id == tenant_id,
            DeploymentDailyMetric.repo_id == repo.id,
            DeploymentDailyMetric.date >= since,
        ).order_by(DeploymentDailyMetric.date.desc())
    )
    metrics = result.scalars().all()

    daily_counts = [
        DailyCount(date=m.date, count=m.deployment_count)
        for m in metrics
    ]
    total = sum(dc.count for dc in daily_counts)

    return DeploymentFrequencyResponse(
        status="ok",
        total=total,
        days=int(days),
        daily_counts=daily_counts,
    )


@router.get("/lead-time")
async def get_lead_time(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    days: DaysWindow = Query(DaysWindow.THIRTY),
) -> LeadTimeResponse:
    # Check for production environment
    env_result = await session.execute(
        select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.repo_id == repo.id,
            Environment.is_production.is_(True),
        ).limit(1)
    )
    if not env_result.scalar_one_or_none():
        return LeadTimeResponse(
            status="setup_required",
            message="no production environment configured",
        )

    since = date.today() - timedelta(days=int(days))
    result = await session.execute(
        select(LeadTimeWeeklyMetric).where(
            LeadTimeWeeklyMetric.tenant_id == tenant_id,
            LeadTimeWeeklyMetric.repo_id == repo.id,
            LeadTimeWeeklyMetric.week_start >= since,
        ).order_by(LeadTimeWeeklyMetric.week_start.desc())
    )
    metrics = result.scalars().all()

    weekly = [
        WeeklyLeadTime(
            week_start=m.week_start,
            median_seconds=m.median_seconds,
            p75_seconds=m.p75_seconds,
            sample_size=m.sample_size,
        )
        for m in metrics
    ]

    # Coverage: attributed PRs / total merged PRs in window
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)

    total_prs_result = await session.execute(
        select(func.count()).select_from(
            select(PullRequest.id).where(
                PullRequest.tenant_id == tenant_id,
                PullRequest.repo_id == repo.id,
                PullRequest.base_ref == repo.default_branch,
                PullRequest.merged_at >= since_dt,
            ).subquery()
        )
    )
    total_prs = total_prs_result.scalar_one()

    attributed_result = await session.execute(
        select(func.count()).select_from(
            select(PullRequest.id).where(
                PullRequest.tenant_id == tenant_id,
                PullRequest.repo_id == repo.id,
                PullRequest.base_ref == repo.default_branch,
                PullRequest.merged_at >= since_dt,
                PullRequest.id.in_(
                    select(DeploymentAttribution.pr_id).where(
                        DeploymentAttribution.tenant_id == tenant_id,
                    )
                ),
            ).subquery()
        )
    )
    attributed_prs = attributed_result.scalar_one()

    coverage = round((attributed_prs / total_prs) * 100, 1) if total_prs > 0 else None

    return LeadTimeResponse(
        status="ok",
        days=int(days),
        coverage_percent=coverage,
        weekly=weekly,
    )


@router.get("/open-prs")
async def get_open_prs(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> OpenPRsResponse:
    result = await session.execute(
        select(
            func.count().label("total"),
            func.sum(func.cast(PullRequest.is_draft == False, sa.Integer)).label("live"),
            func.sum(func.cast(PullRequest.is_draft == True, sa.Integer)).label("draft"),
        ).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo.id,
            PullRequest.base_ref == repo.default_branch,
            PullRequest.merged_at.is_(None),
            PullRequest.closed_at.is_(None),
        )
    )
    row = result.one()
    return OpenPRsResponse(
        total=row.total or 0,
        live=row.live or 0,
        draft=row.draft or 0,
    )


@router.get("/pr-ageing")
async def get_pr_ageing(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> PRAgeingResponse:
    now = func.now()
    age = now - PullRequest.opened_at
    bucket_expr = sa.case(
        (age < sa.text("interval '2 days'"), sa.literal("<2d")),
        (age < sa.text("interval '7 days'"), sa.literal("2-7d")),
        (age < sa.text("interval '14 days'"), sa.literal("7-14d")),
        else_=sa.literal(">14d"),
    ).label("bucket")

    result = await session.execute(
        select(
            bucket_expr,
            func.count().label("count"),
        ).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo.id,
            PullRequest.base_ref == repo.default_branch,
            PullRequest.merged_at.is_(None),
            PullRequest.closed_at.is_(None),
            PullRequest.is_draft.is_(False),
        ).group_by(sa.text("bucket"))
    )
    rows = result.all()
    return PRAgeingResponse(
        buckets=[AgeBucket(bucket=row.bucket, count=row.count) for row in rows],
    )
