from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import REPO_ID, TENANT_ID, make_pr, make_repo, mock_result


@pytest.mark.asyncio
async def test_get_open_pr_count_returns_totals(mock_session):
    from app.services.read_metrics_service import get_open_pr_count

    repo = make_repo(id=REPO_ID)
    row = MagicMock(total=5, live=3, draft=2)
    result_mock = MagicMock()
    result_mock.one.return_value = row
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_open_pr_count(TENANT_ID, repo, mock_session)

    assert result == {"total": 5, "live": 3, "draft": 2}


@pytest.mark.asyncio
async def test_get_open_pr_count_handles_nulls(mock_session):
    from app.services.read_metrics_service import get_open_pr_count

    repo = make_repo(id=REPO_ID)
    row = MagicMock(total=0, live=None, draft=None)
    result_mock = MagicMock()
    result_mock.one.return_value = row
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_open_pr_count(TENANT_ID, repo, mock_session)

    assert result == {"total": 0, "live": 0, "draft": 0}


@pytest.mark.asyncio
async def test_get_pr_ageing_returns_all_buckets_with_counts(mock_session):
    from app.services.read_metrics_service import get_pr_ageing

    repo = make_repo(id=REPO_ID)
    rows = [MagicMock(bucket="<2d", count=2), MagicMock(bucket="2-7d", count=1)]
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_ageing(TENANT_ID, repo, mock_session)

    assert len(result) == 4
    assert result[0] == {"bucket": "<2d", "count": 2}
    assert result[1] == {"bucket": "2-7d", "count": 1}
    assert result[2] == {"bucket": "7-14d", "count": 0}
    assert result[3] == {"bucket": ">14d", "count": 0}


@pytest.mark.asyncio
async def test_get_pr_ageing_empty_returns_all_buckets_zeroed(mock_session):
    from app.services.read_metrics_service import get_pr_ageing

    repo = make_repo(id=REPO_ID)
    result_mock = MagicMock()
    result_mock.all.return_value = []
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_ageing(TENANT_ID, repo, mock_session)

    assert len(result) == 4
    assert all(r["count"] == 0 for r in result)
    assert [r["bucket"] for r in result] == ["<2d", "2-7d", "7-14d", ">14d"]


@pytest.mark.asyncio
async def test_get_deployment_frequency_returns_total_and_daily_counts(mock_session):
    from app.services.read_metrics_service import get_deployment_frequency

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
    from app.services.read_metrics_service import get_deployment_frequency

    repo = make_repo(id=REPO_ID)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[]))

    result = await get_deployment_frequency(TENANT_ID, repo, mock_session, 30)

    assert result["total"] == 0
    assert result["daily_counts"] == []
    assert result["deploys_per_week"] == 0.0


@pytest.mark.asyncio
async def test_get_lead_time_summary_returns_weekly_percentiles(mock_session):
    from app.services.read_metrics_service import get_lead_time_summary

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
    from app.services.read_metrics_service import get_lead_time_summary

    repo = make_repo(id=REPO_ID)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[]))

    result = await get_lead_time_summary(TENANT_ID, repo, mock_session, 30)

    assert result == []


@pytest.mark.asyncio
async def test_get_pr_cycle_time_summary_returns_weekly_percentiles(mock_session):
    from app.services.read_metrics_service import get_pr_cycle_time_summary

    repo = make_repo(id=REPO_ID)
    m1 = MagicMock(week_start=date(2026, 3, 3), median_seconds=1800.0, p75_seconds=3600.0, sample_size=8)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[m1]))

    result = await get_pr_cycle_time_summary(TENANT_ID, repo, mock_session, 30)

    assert len(result) == 1
    assert result[0]["median_seconds"] == 1800.0


@pytest.mark.asyncio
async def test_get_pr_throughput_returns_weekly_counts(mock_session):
    from app.services.read_metrics_service import get_pr_throughput

    repo = make_repo(id=REPO_ID)
    m1 = MagicMock(week_start=date(2026, 3, 3), pr_count=12)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[m1]))

    result = await get_pr_throughput(TENANT_ID, repo, mock_session, 30)

    assert len(result) == 1
    assert result[0]["week_start"] == date(2026, 3, 3)
    assert result[0]["pr_count"] == 12


@pytest.mark.asyncio
async def test_get_pr_throughput_summary_calculates_rate(mock_session):
    from app.services.read_metrics_service import get_pr_throughput_summary

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
    from app.services.read_metrics_service import get_pr_throughput_summary

    repo = make_repo(id=REPO_ID)
    row_mock = MagicMock(total_prs=0, unique_authors=0)
    result_mock = MagicMock()
    result_mock.one.return_value = row_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_throughput_summary(TENANT_ID, repo, mock_session, 30)

    assert result["prs_per_engineer_per_month"] is None


@pytest.mark.asyncio
async def test_get_lead_time_aggregate_computes_median(mock_session):

    from app.services.read_metrics_service import get_lead_time_aggregate

    repo = make_repo(id=REPO_ID)
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    # Lead times: 1h, 2h, 3h — median = 2h = 7200s
    rows = [MagicMock(merged_at=now - timedelta(hours=h + 1), deployed_at=now - timedelta(hours=1)) for h in [1, 2, 3]]
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_lead_time_aggregate(TENANT_ID, repo, mock_session, 30)

    assert result["median_seconds"] == 7200.0
    assert result["sample_size"] == 3


@pytest.mark.asyncio
async def test_get_lead_time_aggregate_empty_returns_none(mock_session):
    from app.services.read_metrics_service import get_lead_time_aggregate

    repo = make_repo(id=REPO_ID)
    result_mock = MagicMock()
    result_mock.all.return_value = []
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_lead_time_aggregate(TENANT_ID, repo, mock_session, 30)

    assert result["median_seconds"] is None
    assert result["sample_size"] == 0


@pytest.mark.asyncio
async def test_get_pr_cycle_time_aggregate_computes_median(mock_session):

    from app.services.read_metrics_service import get_pr_cycle_time_aggregate

    repo = make_repo(id=REPO_ID)
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    # Cycle times: 24h, 48h, 72h — median = 48h = 172800s
    prs = [
        make_pr(
            repo_id=REPO_ID,
            base_ref="main",
            number=i,
            opened_at=now - timedelta(hours=i * 24),
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
    from app.services.read_metrics_service import get_pr_cycle_time_aggregate

    repo = make_repo(id=REPO_ID)
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_cycle_time_aggregate(TENANT_ID, repo, mock_session, 30)

    assert result["median_seconds"] is None
    assert result["sample_size"] == 0
