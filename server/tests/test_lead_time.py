from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import REPO_ID, make_environment


def _make_weekly_metric(week_start: date, median: float, p75: float, sample: int):
    m = MagicMock()
    m.week_start = week_start
    m.median_seconds = median
    m.p75_seconds = p75
    m.sample_size = sample
    return m


@pytest.mark.asyncio
async def test_lead_time_returns_weekly_data(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True)
    m1 = _make_weekly_metric(date(2025, 1, 13), 3600.0, 7200.0, 5)
    m2 = _make_weekly_metric(date(2025, 1, 6), 1800.0, 3600.0, 3)

    env_result = MagicMock()
    env_result.scalars.return_value.all.return_value = [env]

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [m1, m2]
    metrics_result.scalars.return_value = scalars_mock

    agg_result = MagicMock()
    agg_result.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[env_result, metrics_result, agg_result])

    resp = await client.get(f"/metrics/lead-time?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["median_seconds"] is None  # no attributed deploys in aggregate rows
    assert len(data["weekly"]) == 2
    assert data["weekly"][0]["week_start"] == "2025-01-13"
    assert data["weekly"][0]["median_seconds"] == 3600.0
    assert data["weekly"][0]["p75_seconds"] == 7200.0
    assert data["weekly"][0]["sample_size"] == 5


@pytest.mark.asyncio
async def test_lead_time_setup_required(client, mock_session):
    env_result = MagicMock()
    env_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=env_result)

    resp = await client.get(f"/metrics/lead-time?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "setup_required"
    assert data["weekly"] is None


@pytest.mark.asyncio
async def test_lead_time_zero_state(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True)
    env_result = MagicMock()
    env_result.scalars.return_value.all.return_value = [env]

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    metrics_result.scalars.return_value = scalars_mock

    agg_result = MagicMock()
    agg_row = MagicMock()
    agg_row.median_seconds = None
    agg_row.sample_size = 0
    agg_result.one.return_value = agg_row

    mock_session.execute = AsyncMock(side_effect=[env_result, metrics_result, agg_result])

    resp = await client.get(f"/metrics/lead-time?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["weekly"] == []
    assert data["median_seconds"] is None


@pytest.mark.asyncio
async def test_lead_time_custom_window(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True)
    env_result = MagicMock()
    env_result.scalars.return_value.all.return_value = [env]

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    metrics_result.scalars.return_value = scalars_mock

    agg_result = MagicMock()
    agg_row = MagicMock()
    agg_row.median_seconds = None
    agg_row.sample_size = 0
    agg_result.one.return_value = agg_row

    mock_session.execute = AsyncMock(side_effect=[env_result, metrics_result, agg_result])

    resp = await client.get(f"/metrics/lead-time?repo_id={REPO_ID}&window=90")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lead_time_rejects_invalid_window(client, mock_session):
    resp = await client.get(f"/metrics/lead-time?repo_id={REPO_ID}&window=45")
    assert resp.status_code == 422
