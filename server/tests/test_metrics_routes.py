import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import require_auth
from app.db import get_session
from app.main import create_app
from tests.conftest import REPO_ID, TENANT_ID, make_repo


@pytest.fixture
def metrics_client(mock_session):
    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_auth] = lambda: None  # bypass auth in tests
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_recompute_requires_auth(metrics_client):
    resp = await metrics_client.post(
        "/metrics/recompute",
        json={"repo_id": str(REPO_ID)},
    )
    assert resp.status_code == 403  # HTTPBearer rejects missing credentials (FastAPI's HTTPBearer returns 403)


@pytest.mark.asyncio
async def test_recompute_rejects_bad_token(metrics_client):
    resp = await metrics_client.post(
        "/metrics/recompute",
        json={"repo_id": str(REPO_ID)},
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

    with (
        patch("app.routes.metrics.settings") as mock_settings,
        patch("app.routes.metrics.recompute_repo", new_callable=AsyncMock) as mock_recompute,
    ):
        mock_settings.internal_cron_secret = "test-secret"
        mock_recompute.return_value = RecomputeResult(status="success")

        resp = await metrics_client.post(
            "/metrics/recompute",
            json={"repo_id": str(REPO_ID), "tenant_id": str(TENANT_ID)},
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
            "/metrics/recompute",
            json={"repo_id": str(REPO_ID), "tenant_id": str(TENANT_ID)},
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_recompute_targets_requires_auth(metrics_client):
    resp = await metrics_client.get("/metrics/recompute-targets")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recompute_targets_rejects_bad_token(metrics_client):
    resp = await metrics_client.get(
        "/metrics/recompute-targets",
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_recompute_targets_returns_empty_list(metrics_client, mock_session):
    result_mock = MagicMock()
    result_mock.all.return_value = []
    mock_session.execute = AsyncMock(return_value=result_mock)

    with patch("app.routes.metrics.settings") as mock_settings:
        mock_settings.internal_cron_secret = "test-secret"
        resp = await metrics_client.get(
            "/metrics/recompute-targets",
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"targets": [], "count": 0}


@pytest.mark.asyncio
async def test_recompute_targets_returns_sorted_list(metrics_client, mock_session):
    tenant_a = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
    tenant_b = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
    repo_a1 = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
    repo_a2 = uuid.UUID("00000000-0000-0000-0000-0000000000a3")
    repo_b1 = uuid.UUID("00000000-0000-0000-0000-0000000000b2")

    rows = [(tenant_a, repo_a1), (tenant_a, repo_a2), (tenant_b, repo_b1)]
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=result_mock)

    with patch("app.routes.metrics.settings") as mock_settings:
        mock_settings.internal_cron_secret = "test-secret"
        resp = await metrics_client.get(
            "/metrics/recompute-targets",
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    assert body["targets"] == [
        {"tenant_id": str(tenant_a), "repo_id": str(repo_a1)},
        {"tenant_id": str(tenant_a), "repo_id": str(repo_a2)},
        {"tenant_id": str(tenant_b), "repo_id": str(repo_b1)},
    ]


@pytest.mark.asyncio
async def test_unified_endpoint_removed(client):
    resp = await client.get("/metrics/unified?window=30")
    assert resp.status_code == 404
