"""Internal machine-to-machine endpoints for scheduled jobs.

Authenticated with the internal cron secret (not user auth), so they live on
their own routers — this lets main.py apply router-level user auth to every
other non-webhook router without exceptions. The URL paths are pinned:
Railway cron and scripts/run_hourly_recompute.py call them, so the metrics
endpoints keep their historical /metrics/* paths on a separate router.
"""

from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.repository import Repository
from app.rate_limit import limiter
from app.services import invitation_service
from app.services.batch_metrics_service import recompute_repo_and_log

_bearer_scheme = HTTPBearer()


def verify_cron_secret(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    if not settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="cron secret not configured")
    if not hmac.compare_digest(credentials.credentials, settings.internal_cron_secret):
        raise HTTPException(status_code=401, detail="invalid authorization")


router = APIRouter(prefix="/internal", dependencies=[Depends(verify_cron_secret)])
metrics_router = APIRouter(prefix="/metrics", dependencies=[Depends(verify_cron_secret)])


@router.post("/invitations/expire")
async def expire_invitations(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Janitor: mark expired-but-not-redeemed invitations as revoked.

    Inline expiry checks at redeem time are the correctness mechanism; this
    keeps the team page free of stale rows.
    """
    count = await invitation_service.expire_old_invitations(session=session)
    return {"expired": count}


class RecomputeRequest(BaseModel):
    repo_id: uuid.UUID
    tenant_id: uuid.UUID


@metrics_router.post("/recompute")
@limiter.limit("10/minute")
async def recompute_metrics(
    request: Request,
    body: RecomputeRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    repo_result = await session.execute(
        select(Repository).where(
            Repository.id == body.repo_id,
            Repository.tenant_id == body.tenant_id,
        )
    )
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="repo not found")

    result = await recompute_repo_and_log(body.tenant_id, repo, session)
    await session.commit()

    return {"status": result.status, "error_message": result.error_message}


@metrics_router.get("/recompute-targets")
@limiter.limit("10/minute")
async def list_recompute_targets(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Repository.tenant_id, Repository.id).order_by(Repository.tenant_id, Repository.id)
    )
    rows = result.all()
    targets = [{"tenant_id": str(tenant_id), "repo_id": str(repo_id)} for tenant_id, repo_id in rows]
    return {"targets": targets, "count": len(targets)}
