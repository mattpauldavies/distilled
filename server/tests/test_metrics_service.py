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


# --- Read-side query functions ---

from tests.conftest import make_repo, mock_result
from datetime import date


@pytest.mark.asyncio
async def test_get_deployment_frequency_returns_total_and_daily_counts(mock_session):
    from app.services.metrics_service import get_deployment_frequency

    repo = make_repo(id=REPO_ID)
    m1 = MagicMock(date=date(2026, 3, 11), deployment_count=3)
    m2 = MagicMock(date=date(2026, 3, 10), deployment_count=1)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[m1, m2]))

    result = await get_deployment_frequency(TENANT_ID, repo, mock_session, 30)

    assert result["total"] == 4
    assert len(result["daily_counts"]) == 2
    assert result["daily_counts"][0]["date"] == date(2026, 3, 11)
    assert result["daily_counts"][0]["count"] == 3
    assert result["deploys_per_week"] == round(4 / (30 / 7), 1)


@pytest.mark.asyncio
async def test_get_deployment_frequency_empty(mock_session):
    from app.services.metrics_service import get_deployment_frequency

    repo = make_repo(id=REPO_ID)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[]))

    result = await get_deployment_frequency(TENANT_ID, repo, mock_session, 30)

    assert result["total"] == 0
    assert result["daily_counts"] == []
    assert result["deploys_per_week"] == 0.0


@pytest.mark.asyncio
async def test_get_lead_time_summary_returns_weekly_percentiles(mock_session):
    from app.services.metrics_service import get_lead_time_summary

    repo = make_repo(id=REPO_ID)
    m1 = MagicMock(week_start=date(2026, 3, 3), median_seconds=3600.0, p75_seconds=7200.0, sample_size=5)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[m1]))

    result = await get_lead_time_summary(TENANT_ID, repo, mock_session, 30)

    assert len(result) == 1
    assert result[0]["week_start"] == date(2026, 3, 3)
    assert result[0]["median_seconds"] == 3600.0
    assert result[0]["p75_seconds"] == 7200.0
    assert result[0]["sample_size"] == 5


@pytest.mark.asyncio
async def test_get_lead_time_summary_empty(mock_session):
    from app.services.metrics_service import get_lead_time_summary

    repo = make_repo(id=REPO_ID)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[]))

    result = await get_lead_time_summary(TENANT_ID, repo, mock_session, 30)

    assert result == []


@pytest.mark.asyncio
async def test_get_pr_cycle_time_summary_returns_weekly_percentiles(mock_session):
    from app.services.metrics_service import get_pr_cycle_time_summary

    repo = make_repo(id=REPO_ID)
    m1 = MagicMock(week_start=date(2026, 3, 3), median_seconds=1800.0, p75_seconds=3600.0, sample_size=8)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[m1]))

    result = await get_pr_cycle_time_summary(TENANT_ID, repo, mock_session, 30)

    assert len(result) == 1
    assert result[0]["median_seconds"] == 1800.0


@pytest.mark.asyncio
async def test_get_pr_throughput_returns_weekly_counts(mock_session):
    from app.services.metrics_service import get_pr_throughput

    repo = make_repo(id=REPO_ID)
    m1 = MagicMock(week_start=date(2026, 3, 3), pr_count=12)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[m1]))

    result = await get_pr_throughput(TENANT_ID, repo, mock_session, 30)

    assert len(result) == 1
    assert result[0]["week_start"] == date(2026, 3, 3)
    assert result[0]["pr_count"] == 12


@pytest.mark.asyncio
async def test_get_pr_throughput_summary_calculates_rate(mock_session):
    from app.services.metrics_service import get_pr_throughput_summary

    repo = make_repo(id=REPO_ID)
    row_mock = MagicMock(total_prs=12, unique_authors=4)
    result_mock = MagicMock()
    result_mock.one.return_value = row_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_throughput_summary(TENANT_ID, repo, mock_session, 30)

    assert result["total_prs"] == 12
    assert result["unique_authors"] == 4
    # 12 PRs / 4 engineers / (30/30 months) = 3.0
    assert result["prs_per_engineer_per_month"] == 3.0


@pytest.mark.asyncio
async def test_get_pr_throughput_summary_no_authors_returns_none_rate(mock_session):
    from app.services.metrics_service import get_pr_throughput_summary

    repo = make_repo(id=REPO_ID)
    row_mock = MagicMock(total_prs=0, unique_authors=0)
    result_mock = MagicMock()
    result_mock.one.return_value = row_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_throughput_summary(TENANT_ID, repo, mock_session, 30)

    assert result["prs_per_engineer_per_month"] is None


@pytest.mark.asyncio
async def test_get_lead_time_aggregate_computes_median(mock_session):
    from app.services.metrics_service import get_lead_time_aggregate
    from datetime import timezone

    repo = make_repo(id=REPO_ID)
    now = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    # Lead times: 1h, 2h, 3h — median = 2h = 7200s
    rows = [
        MagicMock(merged_at=now - timedelta(hours=h + 1), deployed_at=now - timedelta(hours=1))
        for h in [1, 2, 3]
    ]
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_lead_time_aggregate(TENANT_ID, repo, mock_session, 30)

    assert result["median_seconds"] == 7200.0
    assert result["sample_size"] == 3


@pytest.mark.asyncio
async def test_get_lead_time_aggregate_empty_returns_none(mock_session):
    from app.services.metrics_service import get_lead_time_aggregate

    repo = make_repo(id=REPO_ID)
    result_mock = MagicMock()
    result_mock.all.return_value = []
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_lead_time_aggregate(TENANT_ID, repo, mock_session, 30)

    assert result["median_seconds"] is None
    assert result["sample_size"] == 0


@pytest.mark.asyncio
async def test_get_pr_cycle_time_aggregate_computes_median(mock_session):
    from app.services.metrics_service import get_pr_cycle_time_aggregate
    from datetime import timezone

    repo = make_repo(id=REPO_ID)
    now = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    # Cycle times: 24h, 48h, 72h — median = 48h = 172800s
    prs = [
        make_pr(
            repo_id=REPO_ID,
            base_ref="main",
            number=i,
            opened_at=now - timedelta(hours=(i + 1) * 24),
            merged_at=now,
        )
        for i in [1, 2, 3]
    ]
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = prs
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_cycle_time_aggregate(TENANT_ID, repo, mock_session, 30)

    assert result["median_seconds"] == 172800.0
    assert result["sample_size"] == 3


@pytest.mark.asyncio
async def test_get_pr_cycle_time_aggregate_empty_returns_none(mock_session):
    from app.services.metrics_service import get_pr_cycle_time_aggregate

    repo = make_repo(id=REPO_ID)
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_cycle_time_aggregate(TENANT_ID, repo, mock_session, 30)

    assert result["median_seconds"] is None
    assert result["sample_size"] == 0
