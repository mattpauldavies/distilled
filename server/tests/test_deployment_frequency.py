from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import TENANT_ID, REPO_ID, make_environment


def _make_daily_metric(d: date, count: int):
    m = MagicMock()
    m.date = d
    m.deployment_count = count
    return m


@pytest.mark.asyncio
async def test_deployment_frequency_returns_daily_counts(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True)
    m1 = _make_daily_metric(date(2025, 1, 15), 3)
    m2 = _make_daily_metric(date(2025, 1, 14), 1)

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [m1, m2]
    metrics_result.scalars.return_value = scalars_mock

    mock_session.execute = AsyncMock(side_effect=[env_result, metrics_result])

    resp = await client.get(f"/api/metrics/deployment-frequency?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["total"] == 4
    assert data["days"] == 30
    assert len(data["daily_counts"]) == 2
    assert data["daily_counts"][0]["date"] == "2025-01-15"
    assert data["daily_counts"][0]["count"] == 3


@pytest.mark.asyncio
async def test_deployment_frequency_setup_required(client, mock_session):
    """No production environment → setup_required."""
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=env_result)

    resp = await client.get(f"/api/metrics/deployment-frequency?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "setup_required"
    assert data["total"] is None


@pytest.mark.asyncio
async def test_deployment_frequency_zero_state(client, mock_session):
    """Production env exists but no deployments → total 0."""
    env = make_environment(repo_id=REPO_ID, is_production=True)
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    metrics_result.scalars.return_value = scalars_mock

    mock_session.execute = AsyncMock(side_effect=[env_result, metrics_result])

    resp = await client.get(f"/api/metrics/deployment-frequency?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["total"] == 0
    assert data["daily_counts"] == []


@pytest.mark.asyncio
async def test_deployment_frequency_custom_days(client, mock_session):
    """Accepts days=90 query param."""
    env = make_environment(repo_id=REPO_ID, is_production=True)
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    metrics_result.scalars.return_value = scalars_mock

    mock_session.execute = AsyncMock(side_effect=[env_result, metrics_result])

    resp = await client.get(f"/api/metrics/deployment-frequency?repo_id={REPO_ID}&days=90")

    assert resp.status_code == 200
    assert resp.json()["days"] == 90


@pytest.mark.asyncio
async def test_deployment_frequency_rejects_invalid_days(client, mock_session):
    """Only 30/60/90 allowed."""
    resp = await client.get(f"/api/metrics/deployment-frequency?repo_id={REPO_ID}&days=45")
    assert resp.status_code == 422
