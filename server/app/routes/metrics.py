import hmac
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.config import settings
from app.db import get_session
from app.middleware.repo import get_verified_repo
from app.middleware.tenant import get_tenant_id
from app.models.metrics import MetricsRefreshLog
from app.models.repository import Repository
from app.schemas.metrics import (
    AgeBucket,
    DailyCount,
    DaysWindow,
    DeploymentFrequencyResponse,
    LeadTimeResponse,
    OpenPRsResponse,
    PRAgeingResponse,
    UnifiedDashboardResponse,
    WeeklyPercentiles,
)
from app.services import dashboard_service
from app.services.data_quality_service import get_attribution_coverage
from app.services.environment_service import has_production_environment
from app.services.metrics_service import (
    get_deployment_frequency,
    get_lead_time_summary,
    recompute_repo,
)
from app.services.pull_request_service import get_open_pr_count, get_pr_ageing

router = APIRouter(prefix="/metrics")


class RecomputeRequest(BaseModel):
    repo_id: uuid.UUID


_bearer_scheme = HTTPBearer()


def _verify_cron_secret(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    if not settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="cron secret not configured")
    if not hmac.compare_digest(credentials.credentials, settings.internal_cron_secret):
        raise HTTPException(status_code=401, detail="invalid authorization")


@router.post("/recompute")
async def recompute_metrics(
    body: RecomputeRequest,
    _auth: None = Depends(_verify_cron_secret),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_id = uuid.UUID(settings.seed_tenant_id)

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


@router.get("/deployment-frequency", dependencies=[Depends(require_api_key)])
async def get_deployment_frequency_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    days: DaysWindow = Query(DaysWindow.THIRTY),
) -> DeploymentFrequencyResponse:
    if not await has_production_environment(tenant_id, repo.id, session):
        return DeploymentFrequencyResponse(
            status="setup_required",
            message="no production environment configured",
        )
    result = await get_deployment_frequency(tenant_id, repo, session, int(days))
    return DeploymentFrequencyResponse(
        status="ok",
        total=result["total"],
        days=int(days),
        daily_counts=[DailyCount(**dc) for dc in result["daily_counts"]],
    )


@router.get("/lead-time", dependencies=[Depends(require_api_key)])
async def get_lead_time_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    days: DaysWindow = Query(DaysWindow.THIRTY),
) -> LeadTimeResponse:
    if not await has_production_environment(tenant_id, repo.id, session):
        return LeadTimeResponse(
            status="setup_required",
            message="no production environment configured",
        )
    weekly = await get_lead_time_summary(tenant_id, repo, session, int(days))
    coverage = await get_attribution_coverage(
        tenant_id,
        repo.id,
        repo.default_branch,
        session,
        int(days),
    )
    return LeadTimeResponse(
        status="ok",
        days=int(days),
        coverage_percent=coverage,
        weekly=[WeeklyPercentiles(**w) for w in weekly],
    )


@router.get("/open-prs", dependencies=[Depends(require_api_key)])
async def get_open_prs_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> OpenPRsResponse:
    result = await get_open_pr_count(tenant_id, repo, session)
    return OpenPRsResponse(**result)


@router.get("/pr-ageing", dependencies=[Depends(require_api_key)])
async def get_pr_ageing_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> PRAgeingResponse:
    result = await get_pr_ageing(tenant_id, repo, session)
    return PRAgeingResponse(buckets=[AgeBucket(**b) for b in result])


@router.get("/unified", dependencies=[Depends(require_api_key)])
async def get_unified_dashboard_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> UnifiedDashboardResponse:
    return await dashboard_service.get_unified_dashboard(tenant_id, repo, session, int(window))
