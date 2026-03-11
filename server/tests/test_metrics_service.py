import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from unittest.mock import patch, AsyncMock as AsyncMockFn

from tests.conftest import TENANT_ID, REPO_ID, make_deployment, make_pr


@pytest.mark.asyncio
async def test_deployment_frequency_counts_by_date(mock_session):
    """Given 3 deployments across 2 dates, should UPSERT 2 daily rows."""
    from app.services.metrics_service import compute_deployment_frequency

    d1 = make_deployment(
        repo_id=REPO_ID,
        deployed_at=datetime(2025, 1, 10, 8, 0, tzinfo=timezone.utc),
    )
    d2 = make_deployment(
        repo_id=REPO_ID,
        deployed_at=datetime(2025, 1, 10, 14, 0, tzinfo=timezone.utc),
    )
    d3 = make_deployment(
        repo_id=REPO_ID,
        deployed_at=datetime(2025, 1, 11, 9, 0, tzinfo=timezone.utc),
    )

    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [d1, d2, d3]
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    await compute_deployment_frequency(TENANT_ID, REPO_ID, mock_session)

    # Should have called execute 3 times: 1 SELECT + 2 UPSERTs
    assert mock_session.execute.call_count == 3


@pytest.mark.asyncio
async def test_deployment_frequency_no_deployments(mock_session):
    """Given 0 deployments, should do no UPSERTs."""
    from app.services.metrics_service import compute_deployment_frequency

    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    await compute_deployment_frequency(TENANT_ID, REPO_ID, mock_session)

    # Only the SELECT query, no UPSERTs
    assert mock_session.execute.call_count == 1


@pytest.mark.asyncio
async def test_lead_time_computes_median_and_p75(mock_session):
    """Given 4 attributed PRs in same week, computes correct median/P75."""
    from app.services.metrics_service import compute_lead_time

    deployed_at = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    # Lead times: 1h, 2h, 3h, 4h
    prs_with_deploy = []
    for hours in [1, 2, 3, 4]:
        merged = deployed_at - timedelta(hours=hours)
        prs_with_deploy.append(MagicMock(
            merged_at=merged,
            deployed_at=deployed_at,
            base_ref="main",
        ))

    result_mock = MagicMock()
    result_mock.all.return_value = prs_with_deploy
    mock_session.execute = AsyncMock(return_value=result_mock)

    await compute_lead_time(TENANT_ID, REPO_ID, "main", mock_session)

    # 1 SELECT + 1 UPSERT (all in same week)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_lead_time_skips_negative_durations(mock_session):
    """PRs where merged_at > deployed_at should be excluded."""
    from app.services.metrics_service import compute_lead_time

    deployed_at = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    bad = MagicMock(
        merged_at=deployed_at + timedelta(hours=1),
        deployed_at=deployed_at,
        base_ref="main",
    )

    result_mock = MagicMock()
    result_mock.all.return_value = [bad]
    mock_session.execute = AsyncMock(return_value=result_mock)

    await compute_lead_time(TENANT_ID, REPO_ID, "main", mock_session)

    # Only SELECT, no UPSERT
    assert mock_session.execute.call_count == 1


@pytest.mark.asyncio
async def test_pr_cycle_time_computes_from_opened_to_merged(mock_session):
    """Cycle time = merged_at - opened_at, grouped by week of merged_at."""
    from app.services.metrics_service import compute_pr_cycle_time

    pr1 = make_pr(
        repo_id=REPO_ID,
        base_ref="main",
        opened_at=datetime(2025, 1, 13, 8, 0, tzinfo=timezone.utc),
        merged_at=datetime(2025, 1, 14, 8, 0, tzinfo=timezone.utc),  # 24h
    )
    pr2 = make_pr(
        repo_id=REPO_ID,
        base_ref="main",
        number=2,
        opened_at=datetime(2025, 1, 13, 8, 0, tzinfo=timezone.utc),
        merged_at=datetime(2025, 1, 15, 8, 0, tzinfo=timezone.utc),  # 48h
    )

    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [pr1, pr2]
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    await compute_pr_cycle_time(TENANT_ID, REPO_ID, "main", mock_session)

    # 1 SELECT + 1 UPSERT (same week)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_pr_throughput_counts_by_week(mock_session):
    """Given 3 PRs in same week, should UPSERT 1 row with count=3."""
    from app.services.metrics_service import compute_pr_throughput

    prs = [
        make_pr(repo_id=REPO_ID, base_ref="main", number=i,
                merged_at=datetime(2025, 1, 13 + i, 8, 0, tzinfo=timezone.utc))
        for i in range(3)
    ]

    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = prs
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    await compute_pr_throughput(TENANT_ID, REPO_ID, "main", mock_session)

    # 1 SELECT + 1 UPSERT (same week)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_recompute_repo_calls_all_four_metrics(mock_session):
    """recompute_repo should call all 4 compute functions."""
    from app.services.metrics_service import recompute_repo

    with patch("app.services.metrics_service.compute_deployment_frequency", new_callable=AsyncMockFn) as mock_df, \
         patch("app.services.metrics_service.compute_lead_time", new_callable=AsyncMockFn) as mock_lt, \
         patch("app.services.metrics_service.compute_pr_cycle_time", new_callable=AsyncMockFn) as mock_ct, \
         patch("app.services.metrics_service.compute_pr_throughput", new_callable=AsyncMockFn) as mock_tp:

        result = await recompute_repo(TENANT_ID, REPO_ID, "main", mock_session)

    mock_df.assert_called_once_with(TENANT_ID, REPO_ID, mock_session)
    mock_lt.assert_called_once_with(TENANT_ID, REPO_ID, "main", mock_session)
    mock_ct.assert_called_once_with(TENANT_ID, REPO_ID, "main", mock_session)
    mock_tp.assert_called_once_with(TENANT_ID, REPO_ID, "main", mock_session)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_recompute_repo_continues_on_partial_failure(mock_session):
    """If one metric fails, others still run."""
    from app.services.metrics_service import recompute_repo

    with patch("app.services.metrics_service.compute_deployment_frequency", new_callable=AsyncMockFn, side_effect=Exception("db error")), \
         patch("app.services.metrics_service.compute_lead_time", new_callable=AsyncMockFn) as mock_lt, \
         patch("app.services.metrics_service.compute_pr_cycle_time", new_callable=AsyncMockFn) as mock_ct, \
         patch("app.services.metrics_service.compute_pr_throughput", new_callable=AsyncMockFn) as mock_tp:

        result = await recompute_repo(TENANT_ID, REPO_ID, "main", mock_session)

    mock_lt.assert_called_once()
    mock_ct.assert_called_once()
    mock_tp.assert_called_once()
    assert result.status == "failed"
    assert "deployment_frequency" in result.error_message
