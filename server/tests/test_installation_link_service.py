import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.models.installation_intent import InstallationIntent
from app.models.tenant import Tenant
from app.models.tenant_installation import TenantInstallation
from app.services import installation_link_service
from app.services.installation_link_service import (
    IntentError,
    LinkError,
    add_repos,
    bind_installation,
    claim_by_sender,
    claim_intent,
    create_intent,
    list_available_repos,
    list_workspace_installations,
    remove_repo,
    sync_repos,
    unlink_installation,
)
from tests.conftest import TENANT_ID, make_installation, make_repo, mock_result

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
INSTALLATION_ID = 42
NOW = datetime.now(UTC)


def _compiled(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _scalars(rows):
    result = MagicMock()
    s = MagicMock()
    s.all.return_value = rows
    result.scalars.return_value = s
    result.all = MagicMock(return_value=rows)
    return result


def make_intent(**overrides) -> InstallationIntent:
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        nonce_hash="hash",
        expires_at=NOW + timedelta(minutes=30),
        consumed_at=None,
    )
    defaults.update(overrides)
    return InstallationIntent(**defaults)


def make_link(installation_uuid=None) -> TenantInstallation:
    return TenantInstallation(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        github_installation_id=installation_uuid or uuid.uuid4(),
    )


def make_github(list_repos=None, get_installation=None) -> AsyncMock:
    github = AsyncMock()
    github.list_repos = AsyncMock(return_value=list_repos or [])
    github.get_installation = AsyncMock(
        return_value=get_installation
        or {"id": INSTALLATION_ID, "account": {"login": "acme", "type": "Organization", "id": 777}}
    )
    github.list_environments = AsyncMock(return_value=[])
    github.close = AsyncMock()
    return github


REPO_ONE = {"id": 101, "full_name": "acme/api", "default_branch": "main"}
REPO_TWO = {"id": 102, "full_name": "acme/web", "default_branch": "main"}


# --- create_intent ---


@pytest.mark.asyncio
async def test_create_intent_supersedes_open_intents_and_stores_hash(mock_session):
    mock_session.add = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())

    raw = await create_intent(TENANT_ID, USER_ID, mock_session)

    supersede_sql = _compiled(mock_session.execute.call_args_list[0][0][0])
    assert "UPDATE installation_intents SET" in supersede_sql

    intent = mock_session.add.call_args[0][0]
    assert isinstance(intent, InstallationIntent)
    assert intent.nonce_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert intent.tenant_id == TENANT_ID
    assert intent.user_id == USER_ID
    assert intent.consumed_at is None
    assert intent.expires_at > datetime.now(UTC)
    mock_session.commit.assert_called_once()


# --- claim_intent ---


@pytest.mark.asyncio
async def test_claim_intent_binds_and_consumes(mock_session):
    intent = make_intent()
    tenant = Tenant(id=TENANT_ID, name="My Workspace")
    mock_session.execute = AsyncMock(
        side_effect=[mock_result(scalar_or_none=intent), mock_result(scalar=tenant)]
    )

    with patch.object(installation_link_service, "bind_installation", new=AsyncMock()) as bind:
        result = await claim_intent("nonce", INSTALLATION_ID, USER_ID, mock_session)

    assert result is tenant
    assert intent.consumed_at is not None
    bind.assert_called_once_with(TENANT_ID, INSTALLATION_ID, mock_session)


@pytest.mark.asyncio
async def test_claim_intent_rejects_unknown_nonce(mock_session):
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))
    with pytest.raises(IntentError):
        await claim_intent("nope", INSTALLATION_ID, USER_ID, mock_session)


@pytest.mark.asyncio
async def test_claim_intent_rejects_other_users_nonce(mock_session):
    intent = make_intent(user_id=uuid.uuid4())
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=intent))
    with pytest.raises(IntentError):
        await claim_intent("nonce", INSTALLATION_ID, USER_ID, mock_session)


@pytest.mark.asyncio
async def test_claim_intent_rejects_consumed(mock_session):
    intent = make_intent(consumed_at=NOW)
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=intent))
    with pytest.raises(IntentError):
        await claim_intent("nonce", INSTALLATION_ID, USER_ID, mock_session)


@pytest.mark.asyncio
async def test_claim_intent_rejects_expired(mock_session):
    intent = make_intent(expires_at=NOW - timedelta(minutes=1))
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=intent))
    with pytest.raises(IntentError):
        await claim_intent("nonce", INSTALLATION_ID, USER_ID, mock_session)


# --- claim_by_sender ---


@pytest.mark.asyncio
async def test_claim_by_sender_binds_on_open_intent(mock_session):
    from app.models.user import User

    user = User(id=USER_ID, clerk_user_id="user_x", github_account_id=777)
    intent = make_intent()
    mock_session.execute = AsyncMock(
        side_effect=[mock_result(scalar_or_none=user), mock_result(scalar_or_none=intent)]
    )

    with patch.object(installation_link_service, "bind_installation", new=AsyncMock()) as bind:
        claimed = await claim_by_sender(777, INSTALLATION_ID, mock_session)

    assert claimed is True
    assert intent.consumed_at is not None
    bind.assert_called_once_with(TENANT_ID, INSTALLATION_ID, mock_session)


@pytest.mark.asyncio
async def test_claim_by_sender_unknown_account(mock_session):
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))
    assert await claim_by_sender(999, INSTALLATION_ID, mock_session) is False
    assert mock_session.execute.call_count == 1


@pytest.mark.asyncio
async def test_claim_by_sender_no_open_intent(mock_session):
    from app.models.user import User

    user = User(id=USER_ID, clerk_user_id="user_x", github_account_id=777)
    mock_session.execute = AsyncMock(
        side_effect=[mock_result(scalar_or_none=user), mock_result(scalar_or_none=None)]
    )
    assert await claim_by_sender(777, INSTALLATION_ID, mock_session) is False


# --- bind_installation ---


@pytest.mark.asyncio
async def test_bind_installation_creates_installation_link_and_syncs(mock_session):
    mock_session.add = MagicMock()
    created = make_installation(installation_id=INSTALLATION_ID, account_login="acme")
    repo_rows = [make_repo(github_id=101, full_name="acme/api"), make_repo(github_id=102, full_name="acme/web")]
    mock_session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=None),  # installation lookup
            MagicMock(),  # upsert installation
            mock_result(scalar=created),  # re-select installation
            mock_result(scalar_or_none=None),  # link lookup
            MagicMock(),  # sync repo 1
            MagicMock(),  # sync repo 2
            _scalars(repo_rows),  # repos for env discovery
        ]
    )
    github = make_github(list_repos=[REPO_ONE, REPO_TWO])

    with patch.object(installation_link_service, "GitHubClient", return_value=github):
        installation = await bind_installation(TENANT_ID, INSTALLATION_ID, mock_session)

    assert installation is created

    added_types = [type(call.args[0]).__name__ for call in mock_session.add.call_args_list]
    assert added_types == ["TenantInstallation"]
    github.get_installation.assert_called_once_with(INSTALLATION_ID)
    github.list_repos.assert_called_once_with(INSTALLATION_ID)
    github.close.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_bind_installation_is_idempotent_and_resurrects(mock_session):
    mock_session.add = MagicMock()
    installation = make_installation(installation_id=INSTALLATION_ID, removed_at=NOW)
    link = make_link(installation_uuid=installation.id)
    mock_session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=installation),  # installation lookup
            mock_result(scalar_or_none=link),  # link lookup
            _scalars([]),  # repos for env discovery
        ]
    )
    github = make_github(list_repos=[])

    with patch.object(installation_link_service, "GitHubClient", return_value=github):
        result = await bind_installation(TENANT_ID, INSTALLATION_ID, mock_session)

    assert result is installation
    assert installation.removed_at is None
    mock_session.add.assert_not_called()
    github.get_installation.assert_not_called()


# --- sync_repos: sticky removals ---


@pytest.mark.asyncio
async def test_sync_repos_respect_removed_skips_soft_deleted_rows(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID)

    await sync_repos(TENANT_ID, installation, [REPO_ONE], mock_session, respect_removed=True)
    sql = _compiled(mock_session.execute.call_args[0][0])
    assert "removed_at IS NULL" in sql


@pytest.mark.asyncio
async def test_sync_repos_default_resurrects(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID)

    await sync_repos(TENANT_ID, installation, [REPO_ONE], mock_session)
    sql = _compiled(mock_session.execute.call_args[0][0])
    assert "removed_at IS NULL" not in sql
    assert "ON CONFLICT" in sql


# --- list_workspace_installations ---


@pytest.mark.asyncio
async def test_list_workspace_installations_maps_rows(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID, account_login="acme")
    mock_session.execute = AsyncMock(return_value=_scalars([(installation, 3)]))

    views = await list_workspace_installations(TENANT_ID, mock_session)

    assert len(views) == 1
    assert views[0].installation_id == INSTALLATION_ID
    assert views[0].account_login == "acme"
    assert views[0].repo_count == 3


# --- unlink_installation ---


@pytest.mark.asyncio
async def test_unlink_installation_soft_deletes_repos_and_removes_link(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID)
    link = make_link(installation_uuid=installation.id)
    mock_session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=installation),
            mock_result(scalar_or_none=link),
            MagicMock(),  # repo soft-delete update
        ]
    )

    await unlink_installation(TENANT_ID, INSTALLATION_ID, mock_session)

    update_sql = _compiled(mock_session.execute.call_args_list[2][0][0])
    assert "UPDATE repositories SET removed_at" in update_sql
    mock_session.delete.assert_called_once_with(link)
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_unlink_installation_requires_link(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID)
    mock_session.execute = AsyncMock(
        side_effect=[mock_result(scalar_or_none=installation), mock_result(scalar_or_none=None)]
    )
    with pytest.raises(LinkError):
        await unlink_installation(TENANT_ID, INSTALLATION_ID, mock_session)


# --- list_available_repos ---


@pytest.mark.asyncio
async def test_list_available_repos_annotates_tracked(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID)
    link = make_link(installation_uuid=installation.id)
    mock_session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=installation),
            mock_result(scalar_or_none=link),
            _scalars([101]),  # tracked github_ids
        ]
    )
    github = make_github(list_repos=[REPO_ONE, REPO_TWO])

    with patch.object(installation_link_service, "GitHubClient", return_value=github):
        repos = await list_available_repos(TENANT_ID, INSTALLATION_ID, mock_session)

    by_id = {r.github_id: r for r in repos}
    assert by_id[101].tracked is True
    assert by_id[102].tracked is False
    assert by_id[102].full_name == "acme/web"


@pytest.mark.asyncio
async def test_list_available_repos_requires_link(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID)
    mock_session.execute = AsyncMock(
        side_effect=[mock_result(scalar_or_none=installation), mock_result(scalar_or_none=None)]
    )
    with pytest.raises(LinkError):
        await list_available_repos(TENANT_ID, INSTALLATION_ID, mock_session)


# --- add_repos ---


@pytest.mark.asyncio
async def test_add_repos_validates_and_upserts(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID)
    link = make_link(installation_uuid=installation.id)
    added_row = make_repo(github_id=102, full_name="acme/web")
    mock_session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=installation),
            mock_result(scalar_or_none=link),
            MagicMock(),  # upsert
            _scalars([added_row]),  # re-select added rows
        ]
    )
    github = make_github(list_repos=[REPO_ONE, REPO_TWO])

    with patch.object(installation_link_service, "GitHubClient", return_value=github):
        rows = await add_repos(TENANT_ID, INSTALLATION_ID, [102], mock_session)

    assert rows == [added_row]
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_add_repos_rejects_ungranted_repo(mock_session):
    installation = make_installation(installation_id=INSTALLATION_ID)
    link = make_link(installation_uuid=installation.id)
    mock_session.execute = AsyncMock(
        side_effect=[mock_result(scalar_or_none=installation), mock_result(scalar_or_none=link)]
    )
    github = make_github(list_repos=[REPO_ONE])

    with patch.object(installation_link_service, "GitHubClient", return_value=github):
        with pytest.raises(LinkError):
            await add_repos(TENANT_ID, INSTALLATION_ID, [999], mock_session)


# --- remove_repo ---


@pytest.mark.asyncio
async def test_remove_repo_stamps_removed_at(mock_session):
    repo = make_repo(github_id=101)
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=repo))

    await remove_repo(TENANT_ID, repo.id, mock_session)

    assert repo.removed_at is not None
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_remove_repo_unknown_raises(mock_session):
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))
    with pytest.raises(LinkError):
        await remove_repo(TENANT_ID, uuid.uuid4(), mock_session)
