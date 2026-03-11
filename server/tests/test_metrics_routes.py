import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_session
from app.main import create_app
from tests.conftest import TENANT_ID, REPO_ID, make_repo


@pytest.fixture
def metrics_client(mock_session):
    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_recompute_requires_auth(metrics_client):
    resp = await metrics_client.post(
        "/api/metrics/recompute",
        json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
    )
    assert resp.status_code == 403  # HTTPBearer rejects missing credentials


@pytest.mark.asyncio
async def test_recompute_rejects_bad_token(metrics_client):
    resp = await metrics_client.post(
        "/api/metrics/recompute",
        json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_recompute_success(metrics_client, mock_session):
    from app.services.metrics_service import RecomputeResult

    repo = make_repo(id=REPO_ID, default_branch="main")
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = repo

    # First call returns repo, subsequent calls return default mock
    mock_session.execute = AsyncMock(side_effect=[repo_result, MagicMock(), MagicMock()])

    with patch("app.routes.metrics.settings") as mock_settings, \
         patch("app.routes.metrics.recompute_repo", new_callable=AsyncMock) as mock_recompute:
        mock_settings.internal_cron_secret = "test-secret"
        mock_recompute.return_value = RecomputeResult(status="success")

        resp = await metrics_client.post(
            "/api/metrics/recompute",
            json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_recompute_repo_not_found(metrics_client, mock_session):
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=repo_result)

    with patch("app.routes.metrics.settings") as mock_settings:
        mock_settings.internal_cron_secret = "test-secret"

        resp = await metrics_client.post(
            "/api/metrics/recompute",
            json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 404
