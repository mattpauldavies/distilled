import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import require_api_key


def make_secured_app():
    from fastapi import Depends
    app = FastAPI()

    @app.get("/protected")
    async def protected(_: None = Depends(require_api_key)):
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_missing_auth_header_returns_403():
    """HTTPBearer returns 403 when Authorization header is absent."""
    app = make_secured_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401():
    from unittest.mock import patch
    app = make_secured_app()
    with patch("app.auth.settings") as mock_settings:
        mock_settings.api_key = "correct-key"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unconfigured_api_key_returns_401():
    """When api_key is not configured the dependency must reject all requests."""
    app = make_secured_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"Authorization": "Bearer anything"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_correct_api_key_returns_200():
    from unittest.mock import patch
    app = make_secured_app()
    with patch("app.auth.settings") as mock_settings:
        mock_settings.api_key = "secret-key"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer secret-key"})
    assert resp.status_code == 200
