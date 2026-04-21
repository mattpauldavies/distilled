from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.data_quality_service import MetricsFreshness
from tests.conftest import REPO_ID, make_environment


@pytest.mark.asyncio
async def test_data_quality_returns_all_fields(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True, name="production")

    with (
        patch(
            "app.services.dashboard_service.get_production_environments",
            new_callable=AsyncMock,
        ) as mock_envs,
        patch(
            "app.services.dashboard_service.get_metrics_freshness",
            new_callable=AsyncMock,
        ) as mock_fresh,
        patch(
            "app.services.dashboard_service.get_attribution_coverage",
            new_callable=AsyncMock,
        ) as mock_cov,
    ):
        mock_envs.return_value = [env.name]
        mock_fresh.return_value = MetricsFreshness(
            status="ok",
            last_refresh_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
            days_of_data=47,
        )
        mock_cov.return_value = 87.5

        resp = await client.get(f"/metrics/data-quality?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["attribution_coverage_percent"] == 87.5
    assert data["freshness"]["status"] == "ok"
    assert data["freshness"]["last_refresh_at"] == "2025-01-15T12:00:00Z"
    assert data["freshness"]["days_of_data"] == 47
    assert data["setup"]["has_production_environment"] is True
    assert data["setup"]["production_environments"] == ["production"]


@pytest.mark.asyncio
async def test_data_quality_no_production(client, mock_session):
    with (
        patch(
            "app.services.dashboard_service.get_production_environments",
            new_callable=AsyncMock,
        ) as mock_envs,
        patch(
            "app.services.dashboard_service.get_metrics_freshness",
            new_callable=AsyncMock,
        ) as mock_fresh,
        patch(
            "app.services.dashboard_service.get_attribution_coverage",
            new_callable=AsyncMock,
        ) as mock_cov,
    ):
        mock_envs.return_value = []
        mock_fresh.return_value = MetricsFreshness(
            status="no_data", last_refresh_at=None, days_of_data=None
        )
        mock_cov.return_value = None

        resp = await client.get(f"/metrics/data-quality?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["attribution_coverage_percent"] is None
    assert data["freshness"]["status"] == "no_data"
    assert data["freshness"]["last_refresh_at"] is None
    assert data["freshness"]["days_of_data"] is None
    assert data["setup"]["has_production_environment"] is False
