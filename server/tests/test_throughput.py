from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import REPO_ID


@pytest.mark.asyncio
async def test_throughput_returns_weekly_and_summary(client, mock_session):
    weekly_row = MagicMock()
    weekly_row.week_start = date(2025, 1, 13)
    weekly_row.pr_count = 12

    weekly_result = MagicMock()
    weekly_result.scalars.return_value.all.return_value = [weekly_row]

    summary_row = MagicMock()
    summary_row.total_prs = 12
    summary_row.unique_authors = 3
    summary_result = MagicMock()
    summary_result.one.return_value = summary_row

    mock_session.execute = AsyncMock(side_effect=[weekly_result, summary_result])

    resp = await client.get(f"/metrics/throughput?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["weekly"]) == 1
    assert data["weekly"][0]["pr_count"] == 12
    assert data["total_prs"] == 12
    assert data["unique_authors"] == 3
    assert data["prs_per_engineer_per_month"] == 4.0


@pytest.mark.asyncio
async def test_throughput_zero_state(client, mock_session):
    weekly_result = MagicMock()
    weekly_result.scalars.return_value.all.return_value = []

    summary_row = MagicMock()
    summary_row.total_prs = 0
    summary_row.unique_authors = 0
    summary_result = MagicMock()
    summary_result.one.return_value = summary_row

    mock_session.execute = AsyncMock(side_effect=[weekly_result, summary_result])

    resp = await client.get(f"/metrics/throughput?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["weekly"] == []
    assert data["total_prs"] == 0
    assert data["prs_per_engineer_per_month"] is None


@pytest.mark.asyncio
async def test_throughput_rejects_invalid_window(client, mock_session):
    resp = await client.get(f"/metrics/throughput?repo_id={REPO_ID}&window=45")
    assert resp.status_code == 422
