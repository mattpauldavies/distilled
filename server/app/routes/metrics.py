import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies.repo import get_verified_repo
from app.dependencies.tenant import get_tenant_id
from app.models.repository import Repository
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

router = APIRouter(prefix="/metrics")


@router.get("/deployment-frequency")
async def get_deployment_frequency_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> DeploymentFrequencySection:
    return await dashboard_service.get_deployment_frequency_section(tenant_id, repo, session, int(window))


@router.get("/lead-time")
async def get_lead_time_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> LeadTimeSection:
    return await dashboard_service.get_lead_time_section(tenant_id, repo, session, int(window))


@router.get("/pr-cycle-time")
async def get_pr_cycle_time_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> PRCycleTimeSection:
    return await dashboard_service.get_pr_cycle_time_section(tenant_id, repo, session, int(window))


@router.get("/throughput")
async def get_throughput_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> ThroughputSection:
    return await dashboard_service.get_throughput_section(tenant_id, repo, session, int(window))


@router.get("/open-prs")
async def get_open_prs_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> OpenPRsSection:
    return await dashboard_service.get_open_prs_section(tenant_id, repo, session)


@router.get("/pr-ageing")
async def get_pr_ageing_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> PRAgeingSection:
    return await dashboard_service.get_pr_ageing_section(tenant_id, repo, session)


@router.get("/data-quality")
async def get_data_quality_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> DataQuality:
    return await dashboard_service.get_data_quality_section(tenant_id, repo, session, int(window))
