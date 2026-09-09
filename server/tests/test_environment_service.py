import pytest

from app.services.environment_service import detect_production, discover_environments
from tests.conftest import (
    TENANT_ID,
    make_repo,
    mock_insert_result,
)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("production", True),
        ("prod", True),
        ("live", True),
        ("Production", True),
        ("PROD", True),
        ("distilled / production", True),
        ("production-us", True),
        ("prod-eu", True),
        ("web:live", True),
        ("useast1prod", True),
        # Substring matching is deliberately greedy — see RFC 024.
        ("preprod", True),
        ("staging", False),
        ("dev", False),
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


async def test_discover_environments_marks_namespaced_production(mock_session):
    repo = make_repo()
    mock_session.execute.side_effect = [mock_insert_result(1)]

    await discover_environments(TENANT_ID, repo, [{"name": "distilled / production"}], mock_session)

    stmt = mock_session.execute.call_args_list[0][0][0]
    assert stmt.compile().params["is_production"] is True
