import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.metrics import MetricsRefreshLog
from app.models.repository import Repository
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
