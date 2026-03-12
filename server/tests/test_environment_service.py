import uuid
from unittest.mock import AsyncMock

import pytest

from app.services.environment_service import detect_production, discover_environments, has_production_environment
from tests.conftest import make_repo, make_environment, mock_insert_result, mock_result, TENANT_ID, REPO_ID


@pytest.mark.parametrize(
    "name, expected",
    [
        ("production", True),
        ("prod", True),
        ("live", True),
        ("Production", True),
        ("PROD", True),
        ("staging", False),
        ("dev", False),
        ("production-us", False),
        ("", False),
    ],
)
def test_detect_production(name: str, expected: bool):
    assert detect_production(name) is expected


async def test_has_production_environment_true(mock_session):
    env = make_environment(repo_id=REPO_ID, name="production")
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=env))

    result = await has_production_environment(TENANT_ID, REPO_ID, mock_session)

    assert result is True


async def test_has_production_environment_false(mock_session):
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    result = await has_production_environment(TENANT_ID, REPO_ID, mock_session)

    assert result is False


async def test_discover_environments(mock_session):
    repo = make_repo()
    envs = [{"name": "production"}, {"name": "staging"}]
    mock_session.execute.side_effect = [mock_insert_result(1), mock_insert_result(1)]

    await discover_environments(TENANT_ID, repo, envs, mock_session)

    assert mock_session.execute.call_count == 2


async def test_discover_environments_empty(mock_session):
    repo = make_repo()
    await discover_environments(TENANT_ID, repo, [], mock_session)
    mock_session.execute.assert_not_called()
