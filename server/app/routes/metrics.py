import uuid
from datetime import date, datetime, timedelta, timezone
from enum import IntEnum

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.middleware.repo import get_verified_repo
from app.middleware.tenant import get_tenant_id
from app.models.environment import Environment
from app.models.metrics import DeploymentDailyMetric, MetricsRefreshLog
from app.models.repository import Repository
from app.schemas.metrics import DailyCount, DeploymentFrequencyResponse
from app.services.metrics_service import recompute_repo

router = APIRouter(prefix="/metrics")


class RecomputeRequest(BaseModel):
    tenant_id: uuid.UUID
    repo_id: uuid.UUID


def _verify_cron_secret(authorization: str = Header(...)) -> None:
    if not settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="cron secret not configured")
    expected = f"Bearer {settings.internal_cron_secret}"
    if authorization != expected:
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
