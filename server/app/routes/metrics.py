import hmac
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth
from app.config import settings
from app.db import get_session
from app.middleware.repo import get_verified_repo
from app.middleware.tenant import get_tenant_id
from app.models.metrics import MetricsRefreshLog
from app.models.repository import Repository
from app.rate_limit import limiter
from app.schemas.metrics import (
    DataQuality,
    DaysWindow,
    DeploymentFrequencySection,
    LeadTimeSection,
    OpenPRsSection,
    PRAgeingSection,
    PRCycleTimeSection,
    ThroughputSection,
)
from app.services import dashboard_service
from app.services.metrics_service import recompute_repo

router = APIRouter(prefix="/metrics")


class RecomputeRequest(BaseModel):
    repo_id: uuid.UUID
    tenant_id: uuid.UUID


_bearer_scheme = HTTPBearer()


def _verify_cron_secret(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    if not settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="cron secret not configured")
    if not hmac.compare_digest(credentials.credentials, settings.internal_cron_secret):
        raise HTTPException(status_code=401, detail="invalid authorization")


@router.post("/recompute")
@limiter.limit("10/minute")
async def recompute_metrics(
    request: Request,
    body: RecomputeRequest,
    _auth: None = Depends(_verify_cron_secret),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_id = body.tenant_id

    # Look up repo for default_branch
    repo_result = await session.execute(
        select(Repository).where(
            Repository.id == body.repo_id,
            Repository.tenant_id == tenant_id,
        )
    )
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="repo not found")

    now = datetime.now(UTC)
    hour = now.replace(minute=0, second=0, microsecond=0)

    result = await recompute_repo(
        tenant_id,
        body.repo_id,
        repo.default_branch,
        session,
    )

    # UPSERT refresh log (dedup per hour)
    stmt = (
        insert(MetricsRefreshLog)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=body.repo_id,
            hour=hour,
            started_at=now,
            completed_at=datetime.now(UTC),
            status=result.status,
            error_message=result.error_message,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "hour"],
            set_={
                "started_at": now,
                "completed_at": datetime.now(UTC),
                "status": result.status,
                "error_message": result.error_message,
            },
        )
    )
    await session.execute(stmt)
    await session.commit()

    return {"status": result.status, "error_message": result.error_message}


@router.get("/recompute-targets")
@limiter.limit("10/minute")
async def list_recompute_targets(
    request: Request,
    _auth: None = Depends(_verify_cron_secret),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Repository.tenant_id, Repository.id).order_by(Repository.tenant_id, Repository.id)
    )
    rows = result.all()
    targets = [
        {"tenant_id": str(tenant_id), "repo_id": str(repo_id)} for tenant_id, repo_id in rows
    ]
    return {"targets": targets, "count": len(targets)}


@router.get("/deployment-frequency", dependencies=[Depends(require_auth)])
async def get_deployment_frequency_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> DeploymentFrequencySection:
    return await dashboard_service.get_deployment_frequency_section(
        tenant_id, repo, session, int(window)
    )


@router.get("/lead-time", dependencies=[Depends(require_auth)])
async def get_lead_time_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> LeadTimeSection:
    return await dashboard_service.get_lead_time_section(tenant_id, repo, session, int(window))


@router.get("/pr-cycle-time", dependencies=[Depends(require_auth)])
async def get_pr_cycle_time_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> PRCycleTimeSection:
    return await dashboard_service.get_pr_cycle_time_section(tenant_id, repo, session, int(window))


@router.get("/throughput", dependencies=[Depends(require_auth)])
async def get_throughput_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> ThroughputSection:
    return await dashboard_service.get_throughput_section(tenant_id, repo, session, int(window))


@router.get("/open-prs", dependencies=[Depends(require_auth)])
async def get_open_prs_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> OpenPRsSection:
    return await dashboard_service.get_open_prs_section(tenant_id, repo, session)


@router.get("/pr-ageing", dependencies=[Depends(require_auth)])
async def get_pr_ageing_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> PRAgeingSection:
    return await dashboard_service.get_pr_ageing_section(tenant_id, repo, session)


@router.get("/data-quality", dependencies=[Depends(require_auth)])
async def get_data_quality_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> DataQuality:
    return await dashboard_service.get_data_quality_section(tenant_id, repo, session, int(window))
