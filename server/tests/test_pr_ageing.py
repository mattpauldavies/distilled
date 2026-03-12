from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import REPO_ID


@pytest.mark.asyncio
async def test_pr_ageing_returns_buckets(client, mock_session):
    rows = [
        MagicMock(bucket="<2d", count=2),
        MagicMock(bucket="2-7d", count=3),
        MagicMock(bucket="7-14d", count=1),
        MagicMock(bucket=">14d", count=0),
    ]
    result = MagicMock()
    result.all.return_value = rows

    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/api/metrics/pr-ageing?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["buckets"]) == 4
    assert data["buckets"][0] == {"bucket": "<2d", "count": 2}
    assert data["buckets"][1] == {"bucket": "2-7d", "count": 3}


@pytest.mark.asyncio
async def test_pr_ageing_zero_state(client, mock_session):
    result = MagicMock()
    result.all.return_value = []

    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/api/metrics/pr-ageing?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["buckets"] == []
