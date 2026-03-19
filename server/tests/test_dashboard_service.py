from datetime import date
from unittest.mock import AsyncMock as AM
from unittest.mock import patch

import pytest

from tests.conftest import REPO_ID, TENANT_ID, make_repo


@pytest.mark.asyncio
async def test_get_unified_dashboard_happy_path(mock_session):
    from app.services.dashboard_service import get_unified_dashboard

    repo = make_repo(id=REPO_ID, default_branch="main")

    with (
        patch("app.services.dashboard_service.get_production_environments", new_callable=AM) as mock_prod_envs,
        patch("app.services.dashboard_service.get_deployment_frequency", new_callable=AM) as mock_dep,
        patch("app.services.dashboard_service.get_lead_time_summary", new_callable=AM) as mock_lt,
        patch("app.services.dashboard_service.get_lead_time_aggregate", new_callable=AM) as mock_lt_agg,
        patch("app.services.dashboard_service.get_pr_cycle_time_summary", new_callable=AM) as mock_ct,
        patch("app.services.dashboard_service.get_pr_cycle_time_aggregate", new_callable=AM) as mock_ct_agg,
        patch("app.services.dashboard_service.get_pr_throughput", new_callable=AM) as mock_tp,
        patch("app.services.dashboard_service.get_pr_throughput_summary", new_callable=AM) as mock_tp_summary,
        patch("app.services.dashboard_service.get_open_pr_count", new_callable=AM) as mock_open,
        patch("app.services.dashboard_service.get_pr_ageing", new_callable=AM) as mock_age,
        patch("app.services.dashboard_service.get_metrics_freshness", new_callable=AM) as mock_fresh,
        patch("app.services.dashboard_service.get_attribution_coverage", new_callable=AM) as mock_cov,
    ):
        mock_prod_envs.return_value = ["production"]
        mock_dep.return_value = {
            "total": 5,
            "daily_counts": [{"date": date(2026, 3, 11), "count": 5}],
            "deploys_per_week": 1.2,
        }
        mock_lt.return_value = [
            {"week_start": date(2026, 3, 3), "median_seconds": 3600.0, "p75_seconds": 7200.0, "sample_size": 5}
        ]
        mock_lt_agg.return_value = {"median_seconds": 3600.0, "sample_size": 5}
        mock_ct.return_value = [
            {"week_start": date(2026, 3, 3), "median_seconds": 1800.0, "p75_seconds": 3600.0, "sample_size": 8}
        ]
        mock_ct_agg.return_value = {"median_seconds": 1800.0, "sample_size": 8}
        mock_tp.return_value = [{"week_start": date(2026, 3, 3), "pr_count": 12}]
        mock_tp_summary.return_value = {"total_prs": 12, "unique_authors": 3, "prs_per_engineer_per_month": 4.0}
        mock_open.return_value = {"total": 5, "live": 3, "draft": 2}
        mock_age.return_value = [{"bucket": "<2d", "count": 2}]

        from app.services.data_quality_service import MetricsFreshness

        mock_fresh.return_value = MetricsFreshness(status="ok", last_refresh_at=None)
        mock_cov.return_value = 87.5

        result = await get_unified_dashboard(TENANT_ID, repo, mock_session, 30)

    assert result.deployment_frequency.status == "ok"
    assert result.deployment_frequency.total == 5
    assert result.lead_time.status == "ok"
    assert len(result.lead_time.weekly) == 1
    assert result.pr_cycle_time.status == "ok"
    assert len(result.throughput.weekly) == 1
    assert result.open_prs.total == 5
    assert len(result.pr_ageing.buckets) == 1
    assert result.data_quality.attribution_coverage_percent == 87.5
    assert result.data_quality.freshness.status == "ok"
    assert result.data_quality.setup.has_production_environment is True
    assert result.data_quality.setup.production_environments == ["production"]


@pytest.mark.asyncio
async def test_get_unified_dashboard_no_prod_env(mock_session):
    from app.services.dashboard_service import get_unified_dashboard

    repo = make_repo(id=REPO_ID, default_branch="main")

    with (
        patch("app.services.dashboard_service.get_production_environments", new_callable=AM) as mock_prod_envs,
        patch("app.services.dashboard_service.get_pr_throughput", new_callable=AM) as mock_tp,
        patch("app.services.dashboard_service.get_pr_throughput_summary", new_callable=AM) as mock_tp_summary,
        patch("app.services.dashboard_service.get_open_pr_count", new_callable=AM) as mock_open,
        patch("app.services.dashboard_service.get_pr_ageing", new_callable=AM) as mock_age,
        patch("app.services.dashboard_service.get_metrics_freshness", new_callable=AM) as mock_fresh,
        patch("app.services.dashboard_service.get_attribution_coverage", new_callable=AM) as mock_cov,
    ):
        mock_prod_envs.return_value = []
        mock_tp.return_value = []
        mock_tp_summary.return_value = {"total_prs": 0, "unique_authors": 0, "prs_per_engineer_per_month": None}
        mock_open.return_value = {"total": 0, "live": 0, "draft": 0}
        mock_age.return_value = []

        from app.services.data_quality_service import MetricsFreshness

        mock_fresh.return_value = MetricsFreshness(status="no_data", last_refresh_at=None)
        mock_cov.return_value = None

        result = await get_unified_dashboard(TENANT_ID, repo, mock_session, 30)

    assert result.deployment_frequency.status == "setup_required"
    assert result.deployment_frequency.total is None
    assert result.lead_time.status == "setup_required"
    assert result.pr_cycle_time.status == "setup_required"
    assert result.throughput.weekly == []
    assert result.data_quality.setup.has_production_environment is False
    assert result.data_quality.freshness.status == "no_data"
