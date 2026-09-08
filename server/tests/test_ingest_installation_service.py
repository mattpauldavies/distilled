import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.models.user import User
from app.services.ingest_installation_service import (
    handle_installation_event,
    handle_installation_repositories_event,
    sync_repos,
)
from app.services.webhook_service import SKIPPED
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
        last_active_tenant_id=TENANT_ID,
    )


def _installation_repositories_payload(action: str) -> dict:
    return {
        "action": action,
        "installation": {
            "id": 42,
            "account": {"id": GITHUB_ACCOUNT_ID, "login": "org", "type": "Organization"},
        },
        "repositories_added": [
            {"id": 201, "full_name": "org/new-repo", "name": "new-repo", "private": False},
        ]
        if action == "added"
        else [],
        "repositories_removed": [
            {"id": 101, "full_name": "org/repo-one", "name": "repo-one", "private": False},
        ]
        if action == "removed"
        else [],
        "sender": {"login": "dev"},
    }


def _compiled(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


# --- handle_installation_event ---


@pytest.mark.asyncio
async def test_deleted_soft_deletes_installation_and_repos(mock_session):
    """installation.deleted stamps removed_at on the installation and all its repos."""
    installation = make_installation(installation_id=42)
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=installation),  # installation lookup
        MagicMock(),  # update repositories
        MagicMock(),  # update github_installations
    ]

    payload = _installation_payload(action="deleted")
    await handle_installation_event(payload, mock_session)

    assert mock_session.execute.call_count == 3
    repo_update_sql = _compiled(mock_session.execute.call_args_list[1][0][0])
    installation_update_sql = _compiled(mock_session.execute.call_args_list[2][0][0])
    assert "UPDATE repositories SET removed_at" in repo_update_sql
    assert "UPDATE github_installations SET removed_at" in installation_update_sql


@pytest.mark.asyncio
async def test_deleted_unknown_installation_logs_warning(mock_session):
    """installation.deleted for an installation we don't know logs and skips."""
    mock_session.execute.side_effect = [mock_result(scalar_or_none=None)]

    payload = _installation_payload(action="deleted")
    with patch("app.services.ingest_installation_service.logger") as mock_logger:
        result = await handle_installation_event(payload, mock_session)

    mock_logger.warning.assert_called_once()
    assert mock_session.execute.call_count == 1
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_unhandled_action_returns_skipped(mock_session):
    """Actions we don't handle (e.g. suspend) are reported as skipped, not succeeded."""
    payload = _installation_payload(action="suspend")

    result = await handle_installation_event(payload, mock_session)

    mock_session.execute.assert_not_called()
    assert result == SKIPPED


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.discover_environments", new_callable=AsyncMock)
@patch("app.services.ingest_installation_service.GitHubClient")
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

    membership_result = MagicMock()
    membership_result.scalar_one_or_none.return_value = TENANT_ID

    mock_session.execute.side_effect = [
        user_result,  # User lookup by github_account_id
        membership_result,  # owner membership lookup
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

    with patch("app.services.ingest_installation_service.logger") as mock_logger:
        result = await handle_installation_event(payload, mock_session)

    mock_logger.warning.assert_called_once()
    # No installation upsert should happen
    assert mock_session.execute.call_count == 1
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_handle_created_no_owned_tenant_returns_skipped(mock_session):
    """User exists but owns no tenant — the event is skipped."""
    user = make_test_user()
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=user),  # user lookup
        mock_result(scalar_or_none=None),  # owner membership lookup
    ]

    payload = _installation_payload(action="created")
    with patch("app.services.ingest_installation_service.logger") as mock_logger:
        result = await handle_installation_event(payload, mock_session)

    mock_logger.warning.assert_called_once()
    assert result == SKIPPED


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.discover_environments", new_callable=AsyncMock)
@patch("app.services.ingest_installation_service.GitHubClient")
async def test_handle_created_clears_removed_at_on_conflict(mock_github_cls, mock_discover, mock_session):
    """Re-installing the App resurrects a soft-deleted installation."""
    installation = make_installation()
    test_user = make_test_user()

    mock_github_instance = AsyncMock()
    mock_github_cls.return_value = mock_github_instance
    mock_github_instance.list_environments.return_value = []

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = test_user
    membership_result = MagicMock()
    membership_result.scalar_one_or_none.return_value = TENANT_ID

    mock_session.execute.side_effect = [
        user_result,
        membership_result,
        mock_insert_result(1),  # upsert installation
        mock_result(scalar=installation),
        mock_insert_result(1),
        mock_insert_result(1),
        mock_result(rows=[]),
    ]

    await handle_installation_event(_installation_payload(action="created"), mock_session)

    upsert_sql = _compiled(mock_session.execute.call_args_list[2][0][0])
    assert "removed_at" in upsert_sql.split("DO UPDATE SET")[1]


# --- handle_installation_repositories_event ---


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.discover_environments", new_callable=AsyncMock)
@patch("app.services.ingest_installation_service.GitHubClient")
async def test_repositories_added_syncs_and_discovers(mock_github_cls, mock_discover, mock_session):
    """installation_repositories.added upserts the new repos and discovers their environments."""
    installation = make_installation(installation_id=42)
    new_repo = make_repo(github_id=201, full_name="org/new-repo", installation_id=installation.id)

    mock_github_instance = AsyncMock()
    mock_github_cls.return_value = mock_github_instance
    mock_github_instance.list_environments.return_value = [{"name": "production"}]
    mock_github_instance.close = AsyncMock()

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=installation),  # installation lookup
        mock_insert_result(1),  # upsert new repo
        mock_result(rows=[new_repo]),  # fetch added repos for discovery
    ]

    await handle_installation_repositories_event(_installation_repositories_payload("added"), mock_session)

    assert mock_session.execute.call_count == 3
    mock_github_instance.close.assert_awaited()
    mock_discover.assert_awaited()


@pytest.mark.asyncio
async def test_repositories_added_unknown_installation_logs_warning(mock_session):
    """Events for installations we don't know are logged and skipped."""
    mock_session.execute.side_effect = [mock_result(scalar_or_none=None)]

    with patch("app.services.ingest_installation_service.logger") as mock_logger:
        result = await handle_installation_repositories_event(
            _installation_repositories_payload("added"), mock_session
        )

    mock_logger.warning.assert_called_once()
    assert mock_session.execute.call_count == 1
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_repositories_removed_soft_deletes(mock_session):
    """installation_repositories.removed stamps removed_at on the listed repos."""
    installation = make_installation(installation_id=42)
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=installation),  # installation lookup
        MagicMock(),  # update repositories
    ]

    await handle_installation_repositories_event(_installation_repositories_payload("removed"), mock_session)

    assert mock_session.execute.call_count == 2
    update_sql = _compiled(mock_session.execute.call_args_list[1][0][0])
    assert "UPDATE repositories SET removed_at" in update_sql
    assert "github_id IN" in update_sql


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


@pytest.mark.asyncio
async def test_sync_repos_clears_removed_at_on_conflict(mock_session):
    """Re-adding a soft-deleted repo resurrects it."""
    installation = make_installation()
    repos_data = [{"id": 101, "full_name": "org/repo-one", "name": "repo-one", "private": False}]
    mock_session.execute.side_effect = [mock_insert_result(1)]

    await sync_repos(TENANT_ID, installation, repos_data, mock_session)

    upsert_sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "removed_at" in upsert_sql.split("DO UPDATE SET")[1]


@pytest.mark.asyncio
async def test_sync_repos_preserves_default_branch_when_absent(mock_session):
    """Payloads without default_branch (installation_repositories) must not clobber a known branch."""
    installation = make_installation()
    repos_data = [{"id": 101, "full_name": "org/repo-one", "name": "repo-one", "private": False}]
    mock_session.execute.side_effect = [mock_insert_result(1)]

    await sync_repos(TENANT_ID, installation, repos_data, mock_session)

    upsert_sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "default_branch" not in upsert_sql.split("DO UPDATE SET")[1]


@pytest.mark.asyncio
async def test_sync_repos_updates_default_branch_when_present(mock_session):
    """Payloads that do carry default_branch (installation.created) keep updating it."""
    installation = make_installation()
    repos_data = [
        {"id": 101, "full_name": "org/repo-one", "name": "repo-one", "private": False, "default_branch": "trunk"}
    ]
    mock_session.execute.side_effect = [mock_insert_result(1)]

    await sync_repos(TENANT_ID, installation, repos_data, mock_session)

    upsert_sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "default_branch" in upsert_sql.split("DO UPDATE SET")[1]
