import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from tests.conftest import TENANT_ID, make_repo, mock_result


@pytest.mark.asyncio
async def test_get_verified_repo_returns_repo():
    from app.middleware.repo import get_verified_repo

    repo = make_repo()
    session = AsyncMock()
    session.execute.return_value = mock_result(scalar_or_none=repo)

    result = await get_verified_repo(
        repo_id=repo.id, tenant_id=TENANT_ID, session=session
    )
    assert result.id == repo.id


@pytest.mark.asyncio
async def test_get_verified_repo_404_when_not_found():
    from app.middleware.repo import get_verified_repo

    session = AsyncMock()
    session.execute.return_value = mock_result(scalar_or_none=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_verified_repo(
            repo_id=uuid.uuid4(), tenant_id=TENANT_ID, session=session
        )
    assert exc_info.value.status_code == 404
