import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import CurrentUser, require_auth, require_owner
from app.db import get_session
from app.main import create_app
from app.models.tenant import Tenant
from app.services import membership_service


def _make_client(*, role: str = "owner", tenant: Tenant | None = None, mock_session=None):
    app = create_app()
    tenant_id = (tenant or Tenant(id=uuid.uuid4(), name="acme")).id
    user_id = uuid.uuid4()
    user = CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,  # type: ignore[arg-type]
        clerk_user_id="user_test",
    )

    async def override_session():
        yield mock_session or AsyncMock()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_auth] = lambda: user

    if role == "owner":
        app.dependency_overrides[require_owner] = lambda: user
    # If role != owner, leave require_owner alone — it'll call require_auth
    # (overridden above) and reject because user.role != 'owner'.

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test"), user


@pytest.mark.asyncio
async def test_get_team_returns_members():
    tenant = Tenant(id=uuid.uuid4(), name="acme", slug="acme", rename_prompt_dismissed=False)

    mock_session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    mock_session.execute = AsyncMock(return_value=tenant_result)

    async def fake_list_members(*_a, **_kw):
        return [
            membership_service.MemberView(
                user_id=uuid.uuid4(), email="a@x", github_username="anna", role="owner"
            ),
            membership_service.MemberView(
                user_id=uuid.uuid4(), email="r@x", github_username="ravi", role="member"
            ),
        ]

    import app.services.membership_service as svc

    orig = svc.list_members
    svc.list_members = fake_list_members
    try:
        client, _ = _make_client(role="owner", tenant=tenant, mock_session=mock_session)
        async with client as c:
            resp = await c.get("/team")
    finally:
        svc.list_members = orig

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant"]["name"] == "acme"
    assert body["tenant"]["role"] == "owner"
    assert len(body["members"]) == 2
    assert body["pending_invitations"] == []


@pytest.mark.asyncio
async def test_get_team_forbidden_for_member():
    client, _ = _make_client(role="member")
    async with client as c:
        resp = await c.get("/team")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_team_renames():
    tenant = Tenant(id=uuid.uuid4(), name="old", slug=None, rename_prompt_dismissed=False)

    async def fake_rename(_tenant_id, name, _session):
        tenant.name = name.strip()
        return tenant

    async def fake_dismiss(_tenant_id, _session):
        tenant.rename_prompt_dismissed = True

    import app.services.membership_service as svc

    orig_r, orig_d = svc.rename_tenant, svc.dismiss_rename_prompt
    svc.rename_tenant = fake_rename
    svc.dismiss_rename_prompt = fake_dismiss

    mock_session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    mock_session.execute = AsyncMock(return_value=tenant_result)

    try:
        client, _ = _make_client(role="owner", tenant=tenant, mock_session=mock_session)
        async with client as c:
            resp = await c.patch(
                "/team",
                json={"name": "Acme Engineering", "rename_prompt_dismissed": True},
            )
    finally:
        svc.rename_tenant, svc.dismiss_rename_prompt = orig_r, orig_d

    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Acme Engineering"
    assert tenant.rename_prompt_dismissed is True


@pytest.mark.asyncio
async def test_patch_team_no_changes_returns_400():
    client, _ = _make_client(role="owner")
    async with client as c:
        resp = await c.patch("/team", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_remove_member_self_rejected():
    client, user = _make_client(role="owner")
    async with client as c:
        resp = await c.delete(f"/team/members/{user.user_id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_remove_member_calls_service():
    target_id = uuid.uuid4()

    async def fake_remove(_tenant_id, user_id, _session):
        assert user_id == target_id

    import app.services.membership_service as svc

    orig = svc.remove_member
    svc.remove_member = fake_remove
    try:
        client, _ = _make_client(role="owner")
        async with client as c:
            resp = await c.delete(f"/team/members/{target_id}")
    finally:
        svc.remove_member = orig

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_transfer_ownership_calls_service():
    target_id = uuid.uuid4()

    async def fake_transfer(_tenant_id, *, current_owner_id, new_owner_id, session):
        assert new_owner_id == target_id
        assert session is not None

    import app.services.membership_service as svc

    orig = svc.transfer_ownership
    svc.transfer_ownership = fake_transfer
    try:
        client, _ = _make_client(role="owner")
        async with client as c:
            resp = await c.post(f"/team/members/{target_id}/transfer")
    finally:
        svc.transfer_ownership = orig

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_leave_team_calls_service():
    async def fake_leave(_tenant_id, _user_id, _session):
        return None

    import app.services.membership_service as svc

    orig = svc.leave_tenant
    svc.leave_tenant = fake_leave
    try:
        client, _ = _make_client(role="member")
        async with client as c:
            resp = await c.post("/team/leave")
    finally:
        svc.leave_tenant = orig

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_leave_team_owner_with_others_returns_400():
    async def fake_leave(*_a, **_kw):
        raise membership_service.InvariantViolation("transfer first")

    import app.services.membership_service as svc

    orig = svc.leave_tenant
    svc.leave_tenant = fake_leave
    try:
        client, _ = _make_client(role="owner")
        async with client as c:
            resp = await c.post("/team/leave")
    finally:
        svc.leave_tenant = orig

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_team_calls_service():
    async def fake_delete(_tenant_id, _session):
        return None

    import app.services.membership_service as svc

    orig = svc.delete_tenant
    svc.delete_tenant = fake_delete
    try:
        client, _ = _make_client(role="owner")
        async with client as c:
            resp = await c.delete("/team")
    finally:
        svc.delete_tenant = orig

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_team_with_members_returns_400():
    async def fake_delete(*_a, **_kw):
        raise membership_service.InvariantViolation("has 3 members")

    import app.services.membership_service as svc

    orig = svc.delete_tenant
    svc.delete_tenant = fake_delete
    try:
        client, _ = _make_client(role="owner")
        async with client as c:
            resp = await c.delete("/team")
    finally:
        svc.delete_tenant = orig

    assert resp.status_code == 400
