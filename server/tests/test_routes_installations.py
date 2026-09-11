import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import CurrentUser, require_auth, require_owner, require_user
from app.config import settings
from app.db import get_session
from app.main import create_app
from app.models.tenant import Tenant
from app.models.user import User
from app.services import installation_link_service
from app.services.installation_link_service import (
    AvailableRepo,
    ClaimPending,
    IntentError,
    LinkError,
    WorkspaceInstallationView,
)
from tests.conftest import make_repo

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


def _make_client(*, role: str = "owner", mock_session=None):
    app = create_app()
    current = CurrentUser(
        user_id=USER_ID, tenant_id=TENANT_ID, role=role, clerk_user_id="user_test"  # type: ignore[arg-type]
    )
    user = User(id=USER_ID, clerk_user_id="user_test", last_active_tenant_id=TENANT_ID)

    async def override_session():
        yield mock_session or AsyncMock()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_auth] = lambda: current
    app.dependency_overrides[require_user] = lambda: user
    if role == "owner":
        app.dependency_overrides[require_owner] = lambda: current

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test"), user


# --- POST /installations/intents ---


@pytest.mark.asyncio
async def test_create_intent_returns_install_url(monkeypatch):
    monkeypatch.setattr(settings, "github_app_slug", "distilled-app")
    client, _ = _make_client(role="owner")

    with patch.object(
        installation_link_service, "create_intent", new=AsyncMock(return_value="raw-nonce")
    ) as create_intent:
        async with client as c:
            resp = await c.post("/installations/intents")

    assert resp.status_code == 200, resp.text
    assert (
        resp.json()["install_url"]
        == "https://github.com/apps/distilled-app/installations/new?state=raw-nonce"
    )
    create_intent.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_intent_requires_owner():
    client, _ = _make_client(role="member")
    async with client as c:
        resp = await c.post("/installations/intents")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_intent_fails_without_app_slug(monkeypatch):
    monkeypatch.setattr(settings, "github_app_slug", "")
    client, _ = _make_client(role="owner")
    async with client as c:
        resp = await c.post("/installations/intents")
    assert resp.status_code == 500


# --- POST /installations/claim ---


@pytest.mark.asyncio
async def test_claim_binds_and_returns_workspace():
    tenant = Tenant(id=TENANT_ID, name="My Workspace")
    mock_session = AsyncMock()
    client, user = _make_client(mock_session=mock_session)

    with patch.object(
        installation_link_service, "claim_intent", new=AsyncMock(return_value=tenant)
    ) as claim:
        async with client as c:
            resp = await c.post(
                "/installations/claim", json={"installation_id": 42, "state": "raw-nonce"}
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workspace_id"] == str(TENANT_ID)
    assert body["workspace_name"] == "My Workspace"
    claim.assert_awaited_once()
    assert user.last_active_tenant_id == TENANT_ID


@pytest.mark.asyncio
async def test_claim_org_installation_pending_returns_202():
    """Org installs are bound by the webhook's verified sender; the callback
    answers 202 so the client polls rather than failing."""
    client, user = _make_client()

    with patch.object(
        installation_link_service,
        "claim_intent",
        new=AsyncMock(side_effect=ClaimPending("Waiting for GitHub")),
    ):
        async with client as c:
            resp = await c.post(
                "/installations/claim", json={"installation_id": 42, "state": "raw-nonce"}
            )

    assert resp.status_code == 202, resp.text
    assert resp.json() == {"status": "pending"}
    assert user.last_active_tenant_id == TENANT_ID  # unchanged


@pytest.mark.asyncio
async def test_claim_rejects_bad_state():
    client, _ = _make_client()

    with patch.object(
        installation_link_service,
        "claim_intent",
        new=AsyncMock(side_effect=IntentError("expired")),
    ):
        async with client as c:
            resp = await c.post(
                "/installations/claim", json={"installation_id": 42, "state": "stale"}
            )

    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"]


# --- GET /installations ---


@pytest.mark.asyncio
async def test_list_installations_returns_linked():
    views = [
        WorkspaceInstallationView(
            installation_id=42,
            account_login="acme",
            account_type="organization",
            repo_count=3,
            removed_at=None,
        ),
        WorkspaceInstallationView(
            installation_id=77,
            account_login="mattd",
            account_type="user",
            repo_count=1,
            removed_at=datetime.now(UTC),
        ),
    ]
    client, _ = _make_client()

    with patch.object(
        installation_link_service, "list_workspace_installations", new=AsyncMock(return_value=views)
    ):
        async with client as c:
            resp = await c.get("/installations")

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items[0] == {
        "installation_id": 42,
        "account_login": "acme",
        "account_type": "organization",
        "repo_count": 3,
        "removed": False,
    }
    assert items[1]["removed"] is True


# --- GET /installations/{id}/available-repos ---


@pytest.mark.asyncio
async def test_available_repos_annotated():
    repos = [
        AvailableRepo(github_id=101, full_name="acme/api", default_branch="main", tracked=True),
        AvailableRepo(github_id=102, full_name="acme/web", default_branch="main", tracked=False),
    ]
    client, _ = _make_client(role="owner")

    with patch.object(
        installation_link_service, "list_available_repos", new=AsyncMock(return_value=repos)
    ):
        async with client as c:
            resp = await c.get("/installations/42/available-repos")

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items[0]["tracked"] is True
    assert items[1]["full_name"] == "acme/web"


@pytest.mark.asyncio
async def test_available_repos_unlinked_installation_is_404():
    client, _ = _make_client(role="owner")

    with patch.object(
        installation_link_service,
        "list_available_repos",
        new=AsyncMock(side_effect=LinkError("not connected")),
    ):
        async with client as c:
            resp = await c.get("/installations/42/available-repos")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_available_repos_requires_owner():
    client, _ = _make_client(role="member")
    async with client as c:
        resp = await c.get("/installations/42/available-repos")
    assert resp.status_code == 403


# --- DELETE /installations/{id} ---


@pytest.mark.asyncio
async def test_unlink_installation():
    client, _ = _make_client(role="owner")

    with patch.object(
        installation_link_service, "unlink_installation", new=AsyncMock()
    ) as unlink:
        async with client as c:
            resp = await c.delete("/installations/42")

    assert resp.status_code == 204
    unlink.assert_awaited_once()


@pytest.mark.asyncio
async def test_unlink_installation_unknown_is_404():
    client, _ = _make_client(role="owner")

    with patch.object(
        installation_link_service,
        "unlink_installation",
        new=AsyncMock(side_effect=LinkError("not connected")),
    ):
        async with client as c:
            resp = await c.delete("/installations/42")

    assert resp.status_code == 404


# --- POST /repos ---


@pytest.mark.asyncio
async def test_add_repos_returns_created_rows():
    rows = [make_repo(github_id=102, full_name="acme/web")]
    client, _ = _make_client(role="owner")

    with patch.object(
        installation_link_service, "add_repos", new=AsyncMock(return_value=rows)
    ) as add:
        async with client as c:
            resp = await c.post(
                "/repos", json={"installation_id": 42, "github_ids": [102]}
            )

    assert resp.status_code == 201, resp.text
    assert resp.json()[0]["full_name"] == "acme/web"
    add.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_repos_rejects_ungranted():
    client, _ = _make_client(role="owner")

    with patch.object(
        installation_link_service,
        "add_repos",
        new=AsyncMock(side_effect=LinkError("not granted")),
    ):
        async with client as c:
            resp = await c.post("/repos", json={"installation_id": 42, "github_ids": [999]})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_repos_requires_owner():
    client, _ = _make_client(role="member")
    async with client as c:
        resp = await c.post("/repos", json={"installation_id": 42, "github_ids": [102]})
    assert resp.status_code == 403


# --- DELETE /repos/{repo_id} ---


@pytest.mark.asyncio
async def test_remove_repo():
    client, _ = _make_client(role="owner")

    with patch.object(installation_link_service, "remove_repo", new=AsyncMock()) as remove:
        async with client as c:
            resp = await c.delete(f"/repos/{uuid.uuid4()}")

    assert resp.status_code == 204
    remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_repo_unknown_is_404():
    client, _ = _make_client(role="owner")

    with patch.object(
        installation_link_service,
        "remove_repo",
        new=AsyncMock(side_effect=LinkError("not in this workspace")),
    ):
        async with client as c:
            resp = await c.delete(f"/repos/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_repo_requires_owner():
    client, _ = _make_client(role="member")
    async with client as c:
        resp = await c.delete(f"/repos/{uuid.uuid4()}")
    assert resp.status_code == 403
