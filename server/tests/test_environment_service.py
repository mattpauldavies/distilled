import uuid

import pytest

from app.services.environment_service import detect_production, discover_environments
from tests.conftest import make_repo, mock_insert_result, TENANT_ID


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
