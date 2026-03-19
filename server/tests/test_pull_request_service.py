from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import REPO_ID, TENANT_ID, make_repo


@pytest.mark.asyncio
async def test_get_open_pr_count_returns_totals(mock_session):
    from app.services.pull_request_service import get_open_pr_count

    repo = make_repo(id=REPO_ID)
    row = MagicMock(total=5, live=3, draft=2)
    result_mock = MagicMock()
    result_mock.one.return_value = row
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_open_pr_count(TENANT_ID, repo, mock_session)

    assert result == {"total": 5, "live": 3, "draft": 2}


@pytest.mark.asyncio
async def test_get_open_pr_count_handles_nulls(mock_session):
    from app.services.pull_request_service import get_open_pr_count

    repo = make_repo(id=REPO_ID)
    row = MagicMock(total=0, live=None, draft=None)
    result_mock = MagicMock()
    result_mock.one.return_value = row
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_open_pr_count(TENANT_ID, repo, mock_session)

    assert result == {"total": 0, "live": 0, "draft": 0}


@pytest.mark.asyncio
async def test_get_pr_ageing_returns_all_buckets_with_counts(mock_session):
    from app.services.pull_request_service import get_pr_ageing

    repo = make_repo(id=REPO_ID)
    rows = [MagicMock(bucket="<2d", count=2), MagicMock(bucket="2-7d", count=1)]
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_ageing(TENANT_ID, repo, mock_session)

    assert len(result) == 4
    assert result[0] == {"bucket": "<2d", "count": 2}
    assert result[1] == {"bucket": "2-7d", "count": 1}
    assert result[2] == {"bucket": "7-14d", "count": 0}
    assert result[3] == {"bucket": ">14d", "count": 0}


@pytest.mark.asyncio
async def test_get_pr_ageing_empty_returns_all_buckets_zeroed(mock_session):
    from app.services.pull_request_service import get_pr_ageing

    repo = make_repo(id=REPO_ID)
    result_mock = MagicMock()
    result_mock.all.return_value = []
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_ageing(TENANT_ID, repo, mock_session)

    assert len(result) == 4
    assert all(r["count"] == 0 for r in result)
    assert [r["bucket"] for r in result] == ["<2d", "2-7d", "7-14d", ">14d"]
