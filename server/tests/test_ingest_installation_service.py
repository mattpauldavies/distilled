import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

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
SENDER_ID = 55555


def _installation_payload(action: str = "created", account_type: str = "Organization") -> dict:
    return {
        "action": action,
        "installation": {
            "id": 42,
            "account": {
                "id": GITHUB_ACCOUNT_ID,
                "login": "org",
                "type": account_type,
            },
        },
        "repositories": [
            {"id": 101, "full_name": "org/repo-one", "name": "repo-one", "private": False, "default_branch": "main"},
            {"id": 102, "full_name": "org/repo-two", "name": "repo-two", "private": True, "default_branch": "main"},
        ],
        "sender": {"login": "dev", "id": SENDER_ID},
    }


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
        "sender": {"login": "dev", "id": SENDER_ID},
    }


def _compiled(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _tenant_ids_result(tenant_ids):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = tenant_ids
    result.scalars.return_value = scalars
    return result


# --- handle_installation_event: created ---


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.discover_repo_environments", new_callable=AsyncMock)
@patch("app.services.ingest_installation_service.installation_link_service.claim_by_sender", new_callable=AsyncMock)
async def test_created_claims_via_sender_and_syncs_linked_workspaces(
    mock_claim, mock_discover, mock_session
):
    """An org install with an open intent binds via the webhook sender, then payload
    repos sync into every linked workspace. account.id being an org id is irrelevant —
    the sender drives the claim (the old account-matching heuristic silently dropped
    organisation installs)."""
    mock_claim.return_value = True
    installation = make_installation(installation_id=42, account_login="org")
    repo_rows = [make_repo(github_id=101), make_repo(github_id=102)]
    mock_session.execute.side_effect = [
        mock_insert_result(1),  # upsert global installation
        mock_result(scalar=installation),  # re-select installation
        _tenant_ids_result([TENANT_ID]),  # linked workspaces
        mock_insert_result(1),  # sync repo 1
        mock_insert_result(1),  # sync repo 2
        mock_result(rows=repo_rows),  # repos for env discovery
    ]

    result = await handle_installation_event(_installation_payload(), mock_session)

    assert result is None
    mock_claim.assert_awaited_once_with(SENDER_ID, 42, mock_session)
    upsert_sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "INSERT INTO github_installations" in upsert_sql
    assert "ON CONFLICT" in upsert_sql
    mock_discover.assert_awaited()


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.installation_link_service.claim_by_sender", new_callable=AsyncMock)
async def test_created_without_intent_or_links_is_held_unclaimed(mock_claim, mock_session):
    """No open intent and no existing links: the global installation row is recorded
    but no workspace gets repos."""
    mock_claim.return_value = False
    installation = make_installation(installation_id=42, account_login="org")
    mock_session.execute.side_effect = [
        mock_insert_result(1),  # upsert global installation
        mock_result(scalar=installation),  # re-select installation
        _tenant_ids_result([]),  # no linked workspaces
    ]

    with patch("app.services.ingest_installation_service.logger") as mock_logger:
        result = await handle_installation_event(_installation_payload(), mock_session)

    assert result == SKIPPED
    mock_logger.warning.assert_called_once()
    upsert_sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "INSERT INTO github_installations" in upsert_sql


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.discover_repo_environments", new_callable=AsyncMock)
@patch("app.services.ingest_installation_service.installation_link_service.claim_by_sender", new_callable=AsyncMock)
async def test_created_reinstall_resurrects_and_respects_sticky_removals(
    mock_claim, mock_discover, mock_session
):
    """Re-installing resurrects the installation row; the webhook resync must not
    resurrect repos a workspace deliberately removed."""
    mock_claim.return_value = False
    installation = make_installation(installation_id=42)
    mock_session.execute.side_effect = [
        mock_insert_result(1),  # upsert global installation (clears removed_at)
        mock_result(scalar=installation),  # re-select installation
        _tenant_ids_result([TENANT_ID]),  # linked workspaces
        mock_insert_result(1),  # sync repo 1
        mock_insert_result(1),  # sync repo 2
        mock_result(rows=[]),  # repos for env discovery
    ]

    result = await handle_installation_event(_installation_payload(), mock_session)

    assert result is None
    upsert_sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "removed_at" in upsert_sql.split("DO UPDATE SET")[1]  # re-install resurrects
    sync_sql = _compiled(mock_session.execute.call_args_list[3][0][0])
    assert "removed_at IS NULL" in sync_sql  # respect_removed=True


# --- handle_installation_event: deleted ---


@pytest.mark.asyncio
async def test_deleted_soft_deletes_installation_and_repos_across_workspaces(mock_session):
    installation = make_installation(installation_id=42)
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=installation),  # installation lookup
        MagicMock(),  # update repositories (all linked workspaces)
        MagicMock(),  # update github_installations
    ]

    result = await handle_installation_event(_installation_payload(action="deleted"), mock_session)

    assert result is None
    repo_update_sql = _compiled(mock_session.execute.call_args_list[1][0][0])
    installation_update_sql = _compiled(mock_session.execute.call_args_list[2][0][0])
    assert "UPDATE repositories SET removed_at" in repo_update_sql
    assert "tenant_id" not in repo_update_sql  # spans every linked workspace
    assert "UPDATE github_installations SET removed_at" in installation_update_sql


@pytest.mark.asyncio
async def test_deleted_unknown_installation_logs_warning(mock_session):
    mock_session.execute.side_effect = [mock_result(scalar_or_none=None)]

    with patch("app.services.ingest_installation_service.logger") as mock_logger:
        result = await handle_installation_event(
            _installation_payload(action="deleted"), mock_session
        )

    mock_logger.warning.assert_called_once()
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_unhandled_action_returns_skipped(mock_session):
    result = await handle_installation_event(_installation_payload(action="suspend"), mock_session)
    mock_session.execute.assert_not_called()
    assert result == SKIPPED


# --- handle_installation_repositories_event ---


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.discover_repo_environments", new_callable=AsyncMock)
@patch("app.services.ingest_installation_service.installation_link_service.claim_by_sender", new_callable=AsyncMock)
async def test_repositories_added_fans_out_to_linked_workspaces(
    mock_claim, mock_discover, mock_session
):
    mock_claim.return_value = False
    installation = make_installation(installation_id=42)
    other_tenant = uuid.uuid4()
    new_repo = make_repo(github_id=201, full_name="org/new-repo", installation_id=installation.id)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=installation),  # installation lookup
        _tenant_ids_result([TENANT_ID, other_tenant]),  # linked workspaces
        mock_insert_result(1),  # sync into workspace 1
        mock_result(rows=[new_repo]),  # discovery select 1
        mock_insert_result(1),  # sync into workspace 2
        mock_result(rows=[new_repo]),  # discovery select 2
    ]

    result = await handle_installation_repositories_event(
        _installation_repositories_payload("added"), mock_session
    )

    assert result is None
    mock_claim.assert_awaited_once_with(SENDER_ID, 42, mock_session)
    sync_sql = _compiled(mock_session.execute.call_args_list[2][0][0])
    assert "removed_at IS NULL" in sync_sql  # sticky removals respected
    assert mock_discover.await_count == 2


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.installation_link_service.claim_by_sender", new_callable=AsyncMock)
async def test_repositories_added_unknown_installation_logs_warning(mock_claim, mock_session):
    mock_claim.return_value = False
    mock_session.execute.side_effect = [mock_result(scalar_or_none=None)]

    with patch("app.services.ingest_installation_service.logger") as mock_logger:
        result = await handle_installation_repositories_event(
            _installation_repositories_payload("added"), mock_session
        )

    mock_logger.warning.assert_called_once()
    assert result == SKIPPED


@pytest.mark.asyncio
@patch("app.services.ingest_installation_service.installation_link_service.claim_by_sender", new_callable=AsyncMock)
async def test_repositories_removed_soft_deletes_across_workspaces(mock_claim, mock_session):
    mock_claim.return_value = False
    installation = make_installation(installation_id=42)
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=installation),  # installation lookup
        MagicMock(),  # update repositories
    ]

    result = await handle_installation_repositories_event(
        _installation_repositories_payload("removed"), mock_session
    )

    assert result is None
    update_sql = _compiled(mock_session.execute.call_args_list[1][0][0])
    assert "UPDATE repositories SET removed_at" in update_sql
    assert "github_id IN" in update_sql
    assert "tenant_id" not in update_sql  # spans every linked workspace


# --- sync_repos (shared helper, re-exported for ingest) ---


@pytest.mark.asyncio
async def test_sync_repos(mock_session):
    installation = make_installation(installation_id=42)
    repos_data = [
        {"id": 101, "full_name": "org/repo-one", "default_branch": "main"},
        {"id": 102, "full_name": "org/repo-two", "default_branch": "develop"},
    ]

    await sync_repos(TENANT_ID, installation, repos_data, mock_session)

    assert mock_session.execute.call_count == 2
    sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "INSERT INTO repositories" in sql
    assert "ON CONFLICT" in sql


@pytest.mark.asyncio
async def test_sync_repos_clears_removed_at_on_conflict(mock_session):
    installation = make_installation(installation_id=42)
    repos_data = [{"id": 101, "full_name": "org/repo-one", "default_branch": "main"}]

    await sync_repos(TENANT_ID, installation, repos_data, mock_session)

    sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "removed_at" in sql.split("DO UPDATE SET")[1]


@pytest.mark.asyncio
async def test_sync_repos_preserves_default_branch_when_absent(mock_session):
    installation = make_installation(installation_id=42)
    repos_data = [{"id": 101, "full_name": "org/repo-one"}]

    await sync_repos(TENANT_ID, installation, repos_data, mock_session)

    sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "default_branch" not in sql.split("DO UPDATE SET")[1]


@pytest.mark.asyncio
async def test_sync_repos_updates_default_branch_when_present(mock_session):
    installation = make_installation(installation_id=42)
    repos_data = [{"id": 101, "full_name": "org/repo-one", "default_branch": "trunk"}]

    await sync_repos(TENANT_ID, installation, repos_data, mock_session)

    sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "default_branch" in sql.split("DO UPDATE SET")[1]
