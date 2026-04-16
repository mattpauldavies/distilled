from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import REPO_ID


@pytest.mark.asyncio
async def test_open_prs_returns_counts(client, mock_session):
    result = MagicMock()
    row = MagicMock()
    row.total = 5
    row.live = 3
    row.draft = 2
    result.one.return_value = row

    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/metrics/open-prs?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert data["live"] == 3
    assert data["draft"] == 2


@pytest.mark.asyncio
async def test_open_prs_zero_state(client, mock_session):
    result = MagicMock()
    row = MagicMock()
    row.total = 0
    row.live = 0
    row.draft = 0
    result.one.return_value = row

    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/metrics/open-prs?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["live"] == 0
    assert data["draft"] == 0
