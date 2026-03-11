import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import mock_result, mock_insert_result, make_repo, make_installation, TENANT_ID, NOW
from app.services.installation_service import handle_installation_event, sync_repos


def _installation_payload(action="created"):
    return {
        "action": action,
        "installation": {
            "id": 42,
            "account": {"login": "org", "type": "Organization"},
        },
        "repositories": [
            {"id": 101, "full_name": "org/repo-one", "name": "repo-one", "private": False, "default_branch": "main"},
            {"id": 102, "full_name": "org/repo-two", "name": "repo-two", "private": True, "default_branch": "main"},
        ],
        "sender": {"login": "dev"},
    }


# --- handle_installation_event ---


@pytest.mark.asyncio
async def test_deleted_action_does_nothing(mock_session):
    payload = _installation_payload(action="deleted")
    await handle_installation_event(payload, mock_session)
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.installation_service.discover_environments", new_callable=AsyncMock)
@patch("app.services.installation_service.GitHubClient")
async def test_handle_created(mock_github_cls, mock_discover, mock_session):
    installation = make_installation()
    repo1 = make_repo(github_id=101)
    repo2 = make_repo(github_id=102)

    mock_github_instance = AsyncMock()
    mock_github_cls.return_value = mock_github_instance
    mock_github_instance.list_environments.return_value = [{"name": "production"}]
    mock_github_instance.close = AsyncMock()

    mock_session.flush = AsyncMock()
    mock_session.execute.side_effect = [
        mock_insert_result(1),                      # upsert installation
        mock_result(scalar=installation),           # get installation
        mock_insert_result(1),                      # sync repo 1
        mock_insert_result(1),                      # sync repo 2
        mock_result(rows=[repo1, repo2]),            # get repos after flush
    ]

    payload = _installation_payload(action="created")
    await handle_installation_event(payload, mock_session)

    assert mock_session.flush.call_count >= 1
    mock_github_instance.close.assert_awaited()
    mock_discover.assert_awaited()


# --- sync_repos ---


@pytest.mark.asyncio
async def test_sync_repos(mock_session):
    installation = make_installation()
    repos_data = [
        {"id": 101, "full_name": "org/repo-one", "name": "repo-one", "private": False, "default_branch": "main"},
        {"id": 102, "full_name": "org/repo-two", "name": "repo-two", "private": True, "default_branch": "main"},
    ]

    mock_session.flush = AsyncMock()
    mock_session.execute.side_effect = [
        mock_insert_result(1),
        mock_insert_result(1),
    ]

    await sync_repos(TENANT_ID, installation, repos_data, mock_session)

    assert mock_session.execute.call_count == 2
    mock_session.flush.assert_awaited_once()
