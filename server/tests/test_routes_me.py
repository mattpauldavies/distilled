import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import require_user
from app.db import get_session
from app.main import create_app
from app.models.invitation import Invitation
from app.models.tenant import Tenant
from app.models.user import User
from tests.conftest import mock_result

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


def _make_client(mock_session=None):
    app = create_app()
    user = User(id=USER_ID, clerk_user_id="user_test", last_active_tenant_id=TENANT_ID)

    async def override_session():
        yield mock_session or AsyncMock()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: user

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test"), user


@pytest.mark.asyncio
async def test_list_workspaces_returns_memberships():
    tenant = Tenant(id=TENANT_ID, name="My Workspace", slug=None)
    rows_result = MagicMock()
    rows_result.all.return_value = [(tenant, "owner")]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=rows_result)

    client, _ = _make_client(mock_session)
    async with client as c:
        resp = await c.get("/me/workspaces")

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items == [
        {"id": str(TENANT_ID), "name": "My Workspace", "slug": None, "role": "owner"}
    ]


@pytest.mark.asyncio
async def test_old_tenants_path_is_gone():
    client, _ = _make_client()
    async with client as c:
        resp = await c.get("/me/tenants")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_active_workspace():
    membership = MagicMock()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=membership))

    client, user = _make_client(mock_session)
    target = uuid.uuid4()
    async with client as c:
        resp = await c.post("/me/active-workspace", json={"workspace_id": str(target)})

    assert resp.status_code == 204, resp.text
    assert user.last_active_tenant_id == target


@pytest.mark.asyncio
async def test_set_active_workspace_requires_membership():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    client, _ = _make_client(mock_session)
    async with client as c:
        resp = await c.post("/me/active-workspace", json={"workspace_id": str(uuid.uuid4())})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_old_active_tenant_path_is_gone():
    client, _ = _make_client()
    async with client as c:
        resp = await c.post("/me/active-tenant", json={"tenant_id": str(uuid.uuid4())})
    assert resp.status_code == 404


# --- POST /me/invitations/{id}/accept ---


def make_invitation(**overrides) -> Invitation:
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        email="invitee@example.com",
        token_hash="hash",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        redeemed_at=None,
        revoked_at=None,
    )
    defaults.update(overrides)
    return Invitation(**defaults)


@pytest.mark.asyncio
async def test_accept_invitation_joins_workspace():
    inv = make_invitation()
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=inv),  # invitation lookup
            mock_result(scalar_or_none=None),  # existing membership lookup
        ]
    )
    client, user = _make_client(mock_session)

    with patch(
        "app.routes.me.verifier.get_user_emails",
        new=AsyncMock(return_value=["invitee@example.com"]),
    ):
        async with client as c:
            resp = await c.post(f"/me/invitations/{inv.id}/accept")

    assert resp.status_code == 204, resp.text
    assert inv.redeemed_at is not None
    assert user.last_active_tenant_id == TENANT_ID
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_accept_invitation_rejects_expired():
    """An invitation past expires_at must be rejected even before the expiry
    cron revokes it — the inline check is the correctness mechanism (RFC 021),
    the scheduler is only a janitor."""
    inv = make_invitation(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=inv))
    client, _ = _make_client(mock_session)

    with patch(
        "app.routes.me.verifier.get_user_emails",
        new=AsyncMock(return_value=["invitee@example.com"]),
    ):
        async with client as c:
            resp = await c.post(f"/me/invitations/{inv.id}/accept")

    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()
    assert inv.redeemed_at is None
    mock_session.add.assert_not_called()
