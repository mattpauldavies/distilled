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
async def test_pr_cycle_time_returns_weekly_data(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True)
    m1 = _make_weekly_metric(date(2025, 1, 13), 1800.0, 3600.0, 8)

    env_result = MagicMock()
    env_result.scalars.return_value.all.return_value = [env]

    metrics_result = MagicMock()
    metrics_result.scalars.return_value.all.return_value = [m1]

    agg_result = MagicMock()
    agg_result.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[env_result, metrics_result, agg_result])

    resp = await client.get(f"/metrics/pr-cycle-time?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["weekly"]) == 1
    assert data["weekly"][0]["median_seconds"] == 1800.0


@pytest.mark.asyncio
async def test_pr_cycle_time_setup_required(client, mock_session):
    env_result = MagicMock()
    env_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=env_result)

    resp = await client.get(f"/metrics/pr-cycle-time?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "setup_required"
    assert data["weekly"] is None


@pytest.mark.asyncio
async def test_pr_cycle_time_rejects_invalid_window(client, mock_session):
    resp = await client.get(f"/metrics/pr-cycle-time?repo_id={REPO_ID}&window=45")
    assert resp.status_code == 422
