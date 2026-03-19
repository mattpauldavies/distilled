from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from tests.conftest import (
    REPO_ID,
    TENANT_ID,
    make_environment,
    mock_count_result,
    mock_result,
)

# --- get_metrics_freshness ---


@pytest.mark.asyncio
async def test_freshness_returns_no_data_when_no_records(mock_session):
    from app.services.data_quality_service import get_metrics_freshness

    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    result = await get_metrics_freshness(TENANT_ID, REPO_ID, mock_session)

    assert result.status == "no_data"
    assert result.last_refresh_at is None


@pytest.mark.asyncio
async def test_freshness_returns_ok_when_recent(mock_session):
    from app.services.data_quality_service import get_metrics_freshness

    recent = datetime.now(UTC) - timedelta(minutes=30)
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=recent))

    result = await get_metrics_freshness(TENANT_ID, REPO_ID, mock_session)

    assert result.status == "ok"
    assert result.last_refresh_at == recent


@pytest.mark.asyncio
async def test_freshness_returns_stale_when_old(mock_session):
    from app.services.data_quality_service import get_metrics_freshness

    old = datetime.now(UTC) - timedelta(hours=3)
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=old))

    result = await get_metrics_freshness(TENANT_ID, REPO_ID, mock_session)

    assert result.status == "stale"
    assert result.last_refresh_at == old


@pytest.mark.asyncio
async def test_freshness_boundary_exactly_2h_is_ok(mock_session):
    from app.services.data_quality_service import get_metrics_freshness

    now = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
    boundary = now - timedelta(hours=2)
    mock_session.execute = AsyncMock(return_value=mock_result(scalar_or_none=boundary))

    result = await get_metrics_freshness(TENANT_ID, REPO_ID, mock_session, now=now)

    assert result.status == "ok"


# --- get_production_environments ---


@pytest.mark.asyncio
async def test_production_envs_returns_names(mock_session):
    from app.services.environment_service import get_production_environments

    envs = [
        make_environment(repo_id=REPO_ID, name="production"),
        make_environment(repo_id=REPO_ID, name="staging-prod"),
    ]
    mock_session.execute = AsyncMock(return_value=mock_result(rows=envs))

    result = await get_production_environments(TENANT_ID, REPO_ID, mock_session)

    assert result == ["production", "staging-prod"]


@pytest.mark.asyncio
async def test_production_envs_returns_empty_when_none(mock_session):
    from app.services.environment_service import get_production_environments

    mock_session.execute = AsyncMock(return_value=mock_result(rows=[]))

    result = await get_production_environments(TENANT_ID, REPO_ID, mock_session)

    assert result == []


# --- get_attribution_coverage ---


@pytest.mark.asyncio
async def test_attribution_coverage_computes_percentage(mock_session):
    from app.services.data_quality_service import get_attribution_coverage

    mock_session.execute = AsyncMock(
        side_effect=[
            mock_count_result(10),
            mock_count_result(3),
        ]
    )

    result = await get_attribution_coverage(TENANT_ID, REPO_ID, "main", mock_session)

    assert result == 30.0


@pytest.mark.asyncio
async def test_attribution_coverage_returns_none_when_no_prs(mock_session):
    from app.services.data_quality_service import get_attribution_coverage

    mock_session.execute = AsyncMock(
        side_effect=[
            mock_count_result(0),
            mock_count_result(0),
        ]
    )

    result = await get_attribution_coverage(TENANT_ID, REPO_ID, "main", mock_session)

    assert result is None


@pytest.mark.asyncio
async def test_attribution_coverage_100_percent(mock_session):
    from app.services.data_quality_service import get_attribution_coverage

    mock_session.execute = AsyncMock(
        side_effect=[
            mock_count_result(5),
            mock_count_result(5),
        ]
    )

    result = await get_attribution_coverage(TENANT_ID, REPO_ID, "main", mock_session)

    assert result == 100.0
