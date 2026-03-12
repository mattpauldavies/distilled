import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock as AM

import pytest

from tests.conftest import TENANT_ID, REPO_ID, make_repo, mock_result


# --- get_deployment_frequency ---


@pytest.mark.asyncio
async def test_get_deployment_frequency_returns_total_and_daily_counts(mock_session):
    from app.services.dashboard_service import get_deployment_frequency

    repo = make_repo(id=REPO_ID)

    row1 = MagicMock()
    row1.date = date(2025, 1, 10)
    row1.deployment_count = 2

    row2 = MagicMock()
    row2.date = date(2025, 1, 11)
    row2.deployment_count = 2

    mock_session.execute = AsyncMock(return_value=mock_result(rows=[row1, row2]))

    result = await get_deployment_frequency(TENANT_ID, repo, mock_session, days=30)

    assert result["total"] == 4
    assert len(result["daily_counts"]) == 2
    assert result["daily_counts"][0] == {"date": date(2025, 1, 10), "count": 2}
    assert result["daily_counts"][1] == {"date": date(2025, 1, 11), "count": 2}


@pytest.mark.asyncio
async def test_get_deployment_frequency_empty(mock_session):
    from app.services.dashboard_service import get_deployment_frequency

    repo = make_repo(id=REPO_ID)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[]))

    result = await get_deployment_frequency(TENANT_ID, repo, mock_session, days=30)

    assert result["total"] == 0
    assert result["daily_counts"] == []


# --- get_lead_time_summary ---


@pytest.mark.asyncio
async def test_get_lead_time_summary_returns_weekly_percentiles(mock_session):
    from app.services.dashboard_service import get_lead_time_summary

    repo = make_repo(id=REPO_ID)

    row = MagicMock()
    row.week_start = date(2025, 1, 6)
    row.median_seconds = 3600.0
    row.p75_seconds = 7200.0
    row.sample_size = 10

    mock_session.execute = AsyncMock(return_value=mock_result(rows=[row]))

    result = await get_lead_time_summary(TENANT_ID, repo, mock_session, days=90)

    assert len(result) == 1
    assert result[0]["week_start"] == date(2025, 1, 6)
    assert result[0]["median_seconds"] == 3600.0
    assert result[0]["p75_seconds"] == 7200.0
    assert result[0]["sample_size"] == 10


@pytest.mark.asyncio
async def test_get_lead_time_summary_empty(mock_session):
    from app.services.dashboard_service import get_lead_time_summary

    repo = make_repo(id=REPO_ID)
    mock_session.execute = AsyncMock(return_value=mock_result(rows=[]))

    result = await get_lead_time_summary(TENANT_ID, repo, mock_session, days=90)

    assert result == []


# --- get_pr_cycle_time_summary ---


@pytest.mark.asyncio
async def test_get_pr_cycle_time_summary_returns_weekly_percentiles(mock_session):
    from app.services.dashboard_service import get_pr_cycle_time_summary

    repo = make_repo(id=REPO_ID)

    row = MagicMock()
    row.week_start = date(2025, 1, 6)
    row.median_seconds = 1800.0
    row.p75_seconds = 3600.0
    row.sample_size = 5

    mock_session.execute = AsyncMock(return_value=mock_result(rows=[row]))

    result = await get_pr_cycle_time_summary(TENANT_ID, repo, mock_session, days=90)

    assert len(result) == 1
    assert result[0]["median_seconds"] == 1800.0


# --- get_pr_throughput ---


@pytest.mark.asyncio
async def test_get_pr_throughput_returns_weekly_counts(mock_session):
    from app.services.dashboard_service import get_pr_throughput

    repo = make_repo(id=REPO_ID)

    row = MagicMock()
    row.week_start = date(2025, 1, 6)
    row.pr_count = 8

    mock_session.execute = AsyncMock(return_value=mock_result(rows=[row]))

    result = await get_pr_throughput(TENANT_ID, repo, mock_session, days=90)

    assert len(result) == 1
    assert result[0]["week_start"] == date(2025, 1, 6)
    assert result[0]["pr_count"] == 8


# --- get_open_pr_count ---


@pytest.mark.asyncio
async def test_get_open_pr_count_returns_totals(mock_session):
    from app.services.dashboard_service import get_open_pr_count

    repo = make_repo(id=REPO_ID)

    row = MagicMock()
    row.total = 5
    row.live = 3
    row.draft = 2

    result_mock = MagicMock()
    result_mock.one.return_value = row
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_open_pr_count(TENANT_ID, repo, mock_session)

    assert result == {"total": 5, "live": 3, "draft": 2}


@pytest.mark.asyncio
async def test_get_open_pr_count_handles_nulls(mock_session):
    from app.services.dashboard_service import get_open_pr_count

    repo = make_repo(id=REPO_ID)

    row = MagicMock()
    row.total = 0
    row.live = None
    row.draft = None

    result_mock = MagicMock()
    result_mock.one.return_value = row
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_open_pr_count(TENANT_ID, repo, mock_session)

    assert result == {"total": 0, "live": 0, "draft": 0}


# --- get_pr_ageing ---


@pytest.mark.asyncio
async def test_get_pr_ageing_returns_buckets(mock_session):
    from app.services.dashboard_service import get_pr_ageing

    repo = make_repo(id=REPO_ID)

    row1 = MagicMock()
    row1.bucket = "<2d"
    row1.count = 3

    row2 = MagicMock()
    row2.bucket = "2-7d"
    row2.count = 5

    result_mock = MagicMock()
    result_mock.all.return_value = [row1, row2]
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_ageing(TENANT_ID, repo, mock_session)

    assert len(result) == 2
    assert result[0] == {"bucket": "<2d", "count": 3}
    assert result[1] == {"bucket": "2-7d", "count": 5}


@pytest.mark.asyncio
async def test_get_pr_ageing_empty(mock_session):
    from app.services.dashboard_service import get_pr_ageing

    repo = make_repo(id=REPO_ID)

    result_mock = MagicMock()
    result_mock.all.return_value = []
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await get_pr_ageing(TENANT_ID, repo, mock_session)

    assert result == []


# --- get_unified_dashboard orchestrator ---


@pytest.mark.asyncio
async def test_get_unified_dashboard_happy_path(mock_session):
    from app.services.dashboard_service import get_unified_dashboard

    repo = make_repo(id=REPO_ID, default_branch="main")

    with patch("app.services.dashboard_service.get_production_environments", new_callable=AM) as mock_prod_envs, \
         patch("app.services.dashboard_service.get_deployment_frequency", new_callable=AM) as mock_dep, \
         patch("app.services.dashboard_service.get_lead_time_summary", new_callable=AM) as mock_lt, \
         patch("app.services.dashboard_service.get_pr_cycle_time_summary", new_callable=AM) as mock_ct, \
         patch("app.services.dashboard_service.get_pr_throughput", new_callable=AM) as mock_tp, \
         patch("app.services.dashboard_service.get_open_pr_count", new_callable=AM) as mock_open, \
         patch("app.services.dashboard_service.get_pr_ageing", new_callable=AM) as mock_age, \
         patch("app.services.dashboard_service.get_metrics_freshness", new_callable=AM) as mock_fresh, \
         patch("app.services.dashboard_service.get_attribution_coverage", new_callable=AM) as mock_cov:

        mock_prod_envs.return_value = ["production"]
        mock_dep.return_value = {"total": 5, "daily_counts": [{"date": date(2026, 3, 11), "count": 5}]}
        mock_lt.return_value = [{"week_start": date(2026, 3, 3), "median_seconds": 3600.0, "p75_seconds": 7200.0, "sample_size": 5}]
        mock_ct.return_value = [{"week_start": date(2026, 3, 3), "median_seconds": 1800.0, "p75_seconds": 3600.0, "sample_size": 8}]
        mock_tp.return_value = [{"week_start": date(2026, 3, 3), "pr_count": 12}]
        mock_open.return_value = {"total": 5, "live": 3, "draft": 2}
        mock_age.return_value = [{"bucket": "<2d", "count": 2}]

        from app.services.data_quality_service import MetricsFreshness
        mock_fresh.return_value = MetricsFreshness(status="ok", last_refresh_at=None)
        mock_cov.return_value = 87.5

        result = await get_unified_dashboard(TENANT_ID, repo, mock_session, 30)

    assert result.scheduled.deployment_frequency.status == "ok"
    assert result.scheduled.deployment_frequency.total == 5
    assert result.scheduled.lead_time.status == "ok"
    assert len(result.scheduled.lead_time.weekly) == 1
    assert result.scheduled.pr_cycle_time.status == "ok"
    assert len(result.scheduled.throughput.weekly) == 1
    assert result.live.open_prs.total == 5
    assert len(result.live.pr_ageing.buckets) == 1
    assert result.data_quality.attribution_coverage_percent == 87.5
    assert result.data_quality.freshness.status == "ok"
    assert result.data_quality.setup.has_production_environment is True
    assert result.data_quality.setup.production_environments == ["production"]


@pytest.mark.asyncio
async def test_get_unified_dashboard_no_prod_env(mock_session):
    from app.services.dashboard_service import get_unified_dashboard

    repo = make_repo(id=REPO_ID, default_branch="main")

    with patch("app.services.dashboard_service.get_production_environments", new_callable=AM) as mock_prod_envs, \
         patch("app.services.dashboard_service.get_pr_throughput", new_callable=AM) as mock_tp, \
         patch("app.services.dashboard_service.get_open_pr_count", new_callable=AM) as mock_open, \
         patch("app.services.dashboard_service.get_pr_ageing", new_callable=AM) as mock_age, \
         patch("app.services.dashboard_service.get_metrics_freshness", new_callable=AM) as mock_fresh, \
         patch("app.services.dashboard_service.get_attribution_coverage", new_callable=AM) as mock_cov:

        mock_prod_envs.return_value = []
        mock_tp.return_value = []
        mock_open.return_value = {"total": 0, "live": 0, "draft": 0}
        mock_age.return_value = []

        from app.services.data_quality_service import MetricsFreshness
        mock_fresh.return_value = MetricsFreshness(status="no_data", last_refresh_at=None)
        mock_cov.return_value = None

        result = await get_unified_dashboard(TENANT_ID, repo, mock_session, 30)

    assert result.scheduled.deployment_frequency.status == "setup_required"
    assert result.scheduled.deployment_frequency.total is None
    assert result.scheduled.lead_time.status == "setup_required"
    assert result.scheduled.pr_cycle_time.status == "setup_required"
    assert result.scheduled.throughput.weekly == []
    assert result.data_quality.setup.has_production_environment is False
    assert result.data_quality.freshness.status == "no_data"
