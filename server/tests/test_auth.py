import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import CurrentUser, require_auth, require_owner
from app.db import get_session
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user import User


def make_secured_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(user: CurrentUser = Depends(require_auth)) -> dict:
        return {
            "ok": True,
            "tenant_id": str(user.tenant_id),
            "role": user.role,
        }

    @app.get("/owner-only")
    async def owner_only(user: CurrentUser = Depends(require_owner)) -> dict:
        return {"tenant_id": str(user.tenant_id)}

    return app


def _override_session(app: FastAPI, mock_session) -> None:
    async def override():
        yield mock_session

    app.dependency_overrides[get_session] = override


def _patch_verifier(claims=None):
    return patch(
        "app.auth.verifier.verify_token",
        new=AsyncMock(return_value=claims or {"sub": "user_test123"}),
    )


def _user_membership_executes(*, user, tenant, role: str | None):
    """Build the side_effect list for an auth-path resolution.

    The auth path runs:
      1. user lookup by clerk_user_id
      2. _resolve_active_tenant: either header lookup or fallback chain
    """
    session_executes = []

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    session_executes.append(user_result)

    if role is None:
        # Membership lookup misses
        miss = MagicMock()
        miss.first.return_value = None
        miss.scalar_one_or_none.return_value = None
        session_executes.append(miss)
    else:
        membership_result = MagicMock()
        membership_result.first.return_value = (tenant, role)
        membership_result.scalar_one_or_none.return_value = (tenant, role)
        session_executes.append(membership_result)

    return session_executes


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401():
    app = make_secured_app()
    _override_session(app, AsyncMock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_jwt_returns_401():
    app = make_secured_app()
    _override_session(app, AsyncMock())

    with patch(
        "app.auth.verifier.verify_token",
        new=AsyncMock(
            side_effect=__import__("fastapi").HTTPException(status_code=401, detail="Invalid token")
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer invalid.jwt"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_x_tenant_id_header_resolves_tenant_and_role():
    """Authenticated requests with X-Tenant-Id resolve to the named tenant when membership exists."""
    tenant_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), clerk_user_id="user_test123", last_active_tenant_id=tenant_id)
    tenant = Tenant(id=tenant_id, name="acme")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=_user_membership_executes(user=user, tenant=tenant, role="member")
    )

    app = make_secured_app()
    _override_session(app, mock_session)

    with _patch_verifier():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/protected",
                headers={
                    "Authorization": "Bearer valid.jwt",
                    "X-Tenant-Id": str(tenant_id),
                },
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == str(tenant_id)
    assert body["role"] == "member"


@pytest.mark.asyncio
async def test_missing_header_falls_back_to_last_active_tenant():
    """Without X-Tenant-Id, the user's last_active_tenant_id is used."""
    tenant_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), clerk_user_id="user_test123", last_active_tenant_id=tenant_id)
    tenant = Tenant(id=tenant_id, name="acme")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=_user_membership_executes(user=user, tenant=tenant, role="owner")
    )

    app = make_secured_app()
    _override_session(app, mock_session)

    with _patch_verifier():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer valid.jwt"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "owner"


@pytest.mark.asyncio
async def test_x_tenant_id_for_non_member_returns_403():
    """If the user is not a member of the named tenant, request is forbidden."""
    user = User(id=uuid.uuid4(), clerk_user_id="user_test123", last_active_tenant_id=uuid.uuid4())

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=_user_membership_executes(user=user, tenant=None, role=None)
    )

    app = make_secured_app()
    _override_session(app, mock_session)

    with _patch_verifier():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/protected",
                headers={
                    "Authorization": "Bearer valid.jwt",
                    "X-Tenant-Id": str(uuid.uuid4()),
                },
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_no_memberships_returns_409():
    """An authenticated user with zero memberships returns 409 no_active_tenant."""
    user = User(id=uuid.uuid4(), clerk_user_id="user_test123", last_active_tenant_id=None)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=_user_membership_executes(user=user, tenant=None, role=None)
    )

    app = make_secured_app()
    _override_session(app, mock_session)

    with _patch_verifier():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer valid.jwt"})

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_require_owner_rejects_member():
    """require_owner returns 403 for a member."""
    tenant_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), clerk_user_id="user_test123", last_active_tenant_id=tenant_id)
    tenant = Tenant(id=tenant_id, name="acme")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=_user_membership_executes(user=user, tenant=tenant, role="member")
    )

    app = make_secured_app()
    _override_session(app, mock_session)

    with _patch_verifier():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/owner-only", headers={"Authorization": "Bearer valid.jwt"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_require_owner_allows_owner():
    """require_owner allows an owner."""
    tenant_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), clerk_user_id="user_test123", last_active_tenant_id=tenant_id)
    tenant = Tenant(id=tenant_id, name="acme")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=_user_membership_executes(user=user, tenant=tenant, role="owner")
    )

    app = make_secured_app()
    _override_session(app, mock_session)

    with _patch_verifier():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/owner-only", headers={"Authorization": "Bearer valid.jwt"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant_id"] == str(tenant_id)


@pytest.mark.asyncio
async def test_active_tenant_lazily_persisted():
    """When X-Tenant-Id differs from last_active_tenant_id, the user row is updated."""
    new_tenant_id = uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        clerk_user_id="user_test123",
        last_active_tenant_id=uuid.uuid4(),  # different from new_tenant_id
    )
    tenant = Tenant(id=new_tenant_id, name="acme")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=_user_membership_executes(user=user, tenant=tenant, role="member")
    )

    app = make_secured_app()
    _override_session(app, mock_session)

    with _patch_verifier():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/protected",
                headers={
                    "Authorization": "Bearer valid.jwt",
                    "X-Tenant-Id": str(new_tenant_id),
                },
            )

    assert resp.status_code == 200
    # The user row's last_active should now match the header.
    assert user.last_active_tenant_id == new_tenant_id
    # Commit must have been called to persist that change.
    assert mock_session.commit.await_count >= 1


def test_membership_models_in_use():
    # Smoke check that imports the model — keeps the unused-import linter happy
    # while documenting the auth layer's dependence on TenantUser.
    assert TenantUser.__tablename__ == "tenant_users"
