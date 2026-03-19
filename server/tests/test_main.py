from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_cors_allows_configured_origin():
    """CORS should include Access-Control-Allow-Origin for a configured origin."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.allowed_origins = ["http://localhost:5173"]
        app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health", headers={"Origin": "http://localhost:5173"})

    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_cors_rejects_unknown_origin():
    """CORS should not include Access-Control-Allow-Origin for an unconfigured origin."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.allowed_origins = ["http://localhost:5173"]
        app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health", headers={"Origin": "http://evil.com"})

    assert resp.headers.get("access-control-allow-origin") is None
