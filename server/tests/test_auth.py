import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import CurrentUser, require_auth
from app.db import get_session


def make_secured_app() -> FastAPI:
    """Create a minimal FastAPI app with a protected endpoint."""
    app = FastAPI()

    @app.get("/protected")
    async def protected(user: CurrentUser = Depends(require_auth)) -> dict:
        return {"ok": True, "tenant_id": str(user.tenant_id)}

    return app


@pytest.mark.asyncio
async def test_dev_bypass_returns_seed_tenant_when_jwks_url_not_set():
    """When CLERK_JWKS_URL is empty and environment != production, dev bypass activates."""
    app = make_secured_app()

    mock_session = AsyncMock()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session

    with patch("app.auth.settings") as mock_settings:
        mock_settings.clerk_jwks_url = ""
        mock_settings.environment = "development"
        mock_settings.seed_tenant_id = "00000000-0000-0000-0000-000000000001"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected")

    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_production_with_no_jwks_url_returns_503():
    """When CLERK_JWKS_URL is empty and environment == production, returns 503."""
    app = make_secured_app()

    mock_session = AsyncMock()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session

    with patch("app.auth.settings") as mock_settings:
        mock_settings.clerk_jwks_url = ""
        mock_settings.environment = "production"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_missing_auth_header_returns_403():
    """When CLERK_JWKS_URL is set, missing Authorization header returns 403."""
    app = make_secured_app()

    mock_session = AsyncMock()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session

    with patch("app.auth.settings") as mock_settings:
        mock_settings.clerk_jwks_url = "https://test.clerk.accounts.dev/.well-known/jwks.json"
        mock_settings.environment = "production"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invalid_jwt_returns_401():
    """An invalid JWT token returns 401."""
    app = make_secured_app()

    mock_session = AsyncMock()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session

    with patch("app.auth.settings") as mock_settings, patch(
        "app.auth.verifier.verify_token",
        new=AsyncMock(side_effect=__import__("fastapi").HTTPException(status_code=401, detail="Invalid token")),
    ):
        mock_settings.clerk_jwks_url = "https://test.clerk.accounts.dev/.well-known/jwks.json"
        mock_settings.environment = "production"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer invalid.jwt"})

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_jwt_injects_current_user():
    """A valid JWT results in CurrentUser being injected and the endpoint succeeds."""
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

    from app.models.tenant import Tenant
    from app.models.user import User

    mock_user = User(id=user_id, clerk_user_id="user_test123", tenant_id=tenant_id)
    mock_tenant = Tenant(id=tenant_id, name="testuser")

    app = make_secured_app()

    mock_session = AsyncMock()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session

    with patch("app.auth.settings") as mock_settings, patch(
        "app.auth.verifier.verify_token", new=AsyncMock(return_value={"sub": "user_test123"})
    ), patch(
        "app.auth.get_or_create_user_and_tenant", new=AsyncMock(return_value=(mock_user, mock_tenant))
    ):
        mock_settings.clerk_jwks_url = "https://test.clerk.accounts.dev/.well-known/jwks.json"
        mock_settings.environment = "production"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer valid.jwt"})

    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == str(tenant_id)
