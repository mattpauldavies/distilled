from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_session
from app.main import create_app
from app.schemas.metrics import (
    DataQuality,
    DeploymentFrequencySection,
    FreshnessInfo,
    LeadTimeSection,
    OpenPRsSection,
    PRAgeingSection,
    PRCycleTimeSection,
    SetupInfo,
    ThroughputSection,
    UnifiedDashboardResponse,
)
from tests.conftest import REPO_ID, TENANT_ID, make_repo


@pytest.fixture
def metrics_client(mock_session):
    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_recompute_requires_auth(metrics_client):
    resp = await metrics_client.post(
        "/api/metrics/recompute",
        json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
    )
    assert resp.status_code == 403  # HTTPBearer rejects missing credentials


@pytest.mark.asyncio
async def test_recompute_rejects_bad_token(metrics_client):
    resp = await metrics_client.post(
        "/api/metrics/recompute",
        json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_recompute_success(metrics_client, mock_session):
    from app.services.metrics_service import RecomputeResult

    repo = make_repo(id=REPO_ID, default_branch="main")
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = repo

    # First call returns repo, subsequent calls return default mock
    mock_session.execute = AsyncMock(side_effect=[repo_result, MagicMock(), MagicMock()])

    with patch("app.routes.metrics.settings") as mock_settings, \
         patch("app.routes.metrics.recompute_repo", new_callable=AsyncMock) as mock_recompute:
        mock_settings.internal_cron_secret = "test-secret"
        mock_recompute.return_value = RecomputeResult(status="success")

        resp = await metrics_client.post(
            "/api/metrics/recompute",
            json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_recompute_repo_not_found(metrics_client, mock_session):
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=repo_result)

    with patch("app.routes.metrics.settings") as mock_settings:
        mock_settings.internal_cron_secret = "test-secret"

        resp = await metrics_client.post(
            "/api/metrics/recompute",
            json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unified_endpoint_returns_full_dashboard(client, mock_session):
    mock_response = UnifiedDashboardResponse(
        deployment_frequency=DeploymentFrequencySection(status="ok", total=5, days=30, daily_counts=[]),
        lead_time=LeadTimeSection(status="ok", weekly=[]),
        pr_cycle_time=PRCycleTimeSection(status="ok", weekly=[]),
        throughput=ThroughputSection(weekly=[]),
        open_prs=OpenPRsSection(total=3, live=2, draft=1),
        pr_ageing=PRAgeingSection(buckets=[]),
        data_quality=DataQuality(
            attribution_coverage_percent=87.5,
            freshness=FreshnessInfo(status="ok", last_refresh_at=None),
            setup=SetupInfo(has_production_environment=True, production_environments=["production"]),
        ),
    )

    with patch("app.routes.metrics.dashboard_service.get_unified_dashboard", new_callable=AsyncMock) as mock_unified:
        mock_unified.return_value = mock_response
        resp = await client.get("/api/metrics/unified?window=30")

    assert resp.status_code == 200
    data = resp.json()
    assert data["deployment_frequency"]["status"] == "ok"
    assert data["open_prs"]["total"] == 3
    assert data["data_quality"]["attribution_coverage_percent"] == 87.5


@pytest.mark.asyncio
async def test_unified_endpoint_accepts_180_day_window(client, mock_session):
    mock_response = UnifiedDashboardResponse(
        deployment_frequency=DeploymentFrequencySection(status="ok", total=24, days=180, daily_counts=[]),
        lead_time=LeadTimeSection(status="ok", weekly=[]),
        pr_cycle_time=PRCycleTimeSection(status="ok", weekly=[]),
        throughput=ThroughputSection(weekly=[]),
        open_prs=OpenPRsSection(total=0, live=0, draft=0),
        pr_ageing=PRAgeingSection(buckets=[]),
        data_quality=DataQuality(
            attribution_coverage_percent=None,
            freshness=FreshnessInfo(status="no_data", last_refresh_at=None),
            setup=SetupInfo(has_production_environment=True, production_environments=["production"]),
        ),
    )

    with patch("app.routes.metrics.dashboard_service.get_unified_dashboard", new_callable=AsyncMock) as mock_unified:
        mock_unified.return_value = mock_response
        resp = await client.get("/api/metrics/unified?window=180")

    assert resp.status_code == 200
    data = resp.json()
    assert data["deployment_frequency"]["days"] == 180


@pytest.mark.asyncio
async def test_unified_endpoint_rejects_7_day_window(client, mock_session):
    resp = await client.get("/api/metrics/unified?window=7")
    assert resp.status_code == 422
