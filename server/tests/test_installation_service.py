import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.user import User
from app.services.installation_service import handle_installation_event, sync_repos
from tests.conftest import (
    TENANT_ID,
    make_installation,
    make_repo,
    mock_insert_result,
    mock_result,
)

GITHUB_ACCOUNT_ID = 98765


def _installation_payload(action: str = "created", github_account_id: int = GITHUB_ACCOUNT_ID) -> dict:
    return {
        "action": action,
        "installation": {
            "id": 42,
            "account": {
                "id": github_account_id,
                "login": "org",
                "type": "Organization",
            },
        },
        "repositories": [
            {"id": 101, "full_name": "org/repo-one", "name": "repo-one", "private": False, "default_branch": "main"},
            {"id": 102, "full_name": "org/repo-two", "name": "repo-two", "private": True, "default_branch": "main"},
        ],
        "sender": {"login": "dev"},
    }


def make_test_user(github_account_id: int = GITHUB_ACCOUNT_ID) -> User:
    return User(
        id=uuid.uuid4(),
        clerk_user_id="user_test123",
        github_account_id=github_account_id,
        tenant_id=TENANT_ID,
    )


# --- handle_installation_event ---


@pytest.mark.asyncio
async def test_deleted_action_does_nothing(mock_session):
    payload = _installation_payload(action="deleted")
    await handle_installation_event(payload, mock_session)
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.installation_service.discover_environments", new_callable=AsyncMock)
@patch("app.services.installation_service.GitHubClient")
async def test_handle_created_known_account(mock_github_cls, mock_discover, mock_session):
    """When github_account_id matches a User, installation is linked to their tenant."""
    installation = make_installation()
    repo1 = make_repo(github_id=101)
    repo2 = make_repo(github_id=102)
    test_user = make_test_user()

    mock_github_instance = AsyncMock()
    mock_github_cls.return_value = mock_github_instance
    mock_github_instance.list_environments.return_value = [{"name": "production"}]
    mock_github_instance.close = AsyncMock()

    mock_session.flush = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = test_user

    mock_session.execute.side_effect = [
        user_result,  # User lookup by github_account_id
        mock_insert_result(1),  # upsert installation
        mock_result(scalar=installation),  # get installation
        mock_insert_result(1),  # sync repo 1
        mock_insert_result(1),  # sync repo 2
        mock_result(rows=[repo1, repo2]),  # get repos after flush
    ]

    payload = _installation_payload(action="created")
    await handle_installation_event(payload, mock_session)

    assert mock_session.flush.call_count >= 1
    mock_github_instance.close.assert_awaited()
    mock_discover.assert_awaited()


@pytest.mark.asyncio
async def test_handle_created_unknown_account_logs_warning(mock_session):
    """When github_account_id does not match any User, a warning is logged and the event is skipped."""
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=user_result)

    payload = _installation_payload(action="created", github_account_id=99999)

    with patch("app.services.installation_service.logger") as mock_logger:
        await handle_installation_event(payload, mock_session)

    mock_logger.warning.assert_called_once()
    # No installation upsert should happen
    assert mock_session.execute.call_count == 1


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
