"""Smoke tests for Distilled.

These tests verify essential app functionality against a running server seeded
with demo data. They focus on metric accuracy — the seed data is deterministic
(random.Random(42), two repos over 26 weeks) so the key counts and ranges are
knowable in advance.

Run locally (server + demo data must be up):
    pytest tests/smoke/ -v

Target a remote environment:
    SMOKE_BASE_URL=https://api.example.com pytest tests/smoke/ -v
"""

import httpx
import pytest

# ── Demo seed constants ────────────────────────────────────────────────────────
# From server/scripts/seed_demo.py — these values never change.

WEB_OPEN_TOTAL = 12  # 12 open/draft PRs seeded for acme-corp/web
WEB_OPEN_LIVE = 9   # non-draft
WEB_OPEN_DRAFT = 3  # is_draft=True

API_OPEN_TOTAL = 10  # 10 open/draft PRs seeded for acme-corp/api
API_OPEN_LIVE = 8   # non-draft
API_OPEN_DRAFT = 2  # is_draft=True

# WEB PR ageing bucket counts (based on days_ago in seed specs)
# These are stable because PRs are stored with fixed opened_at offsets and
# the buckets are computed against "now" at query time.
# Buckets can shift by ±1 near boundaries, so we allow a tolerance of ±1.
WEB_AGEING = {"<2d": 3, "2-7d": 2, "7-14d": 3, ">14d": 4}
API_AGEING = {"<2d": 1, "2-7d": 3, "7-14d": 2, ">14d": 4}

# Deployment frequency seed params (random.Random(42) is fixed but week
# boundaries shift with calendar time, so we use generous ±30% ranges).
# web params: 4–5 deploys/week; api: 0–4/week depending on phase.
WEB_DEPLOYS_30D_MIN = 12   # 4/wk × ~4 weeks, conservative
WEB_DEPLOYS_30D_MAX = 30   # 5/wk × ~4 weeks, generous
WEB_DEPLOYS_90D_MIN = 40   # 4/wk × ~13 weeks, conservative
WEB_DEPLOYS_90D_MAX = 80   # 5/wk × ~13 weeks, generous

# WEB PR cycle time: seed params are 4–8 hours (14400–28800 s).
# Allow 2× headroom for p75 and randomness.
WEB_CYCLE_MEDIAN_MIN_S = 3_600    # 1 hour
WEB_CYCLE_MEDIAN_MAX_S = 57_600   # 16 hours

# WEB lead time: PRs open ~4–8 hours before merge, then deployed same/next day.
# Median lead time is roughly cycle time + deployment lag.
WEB_LEAD_MEDIAN_MIN_S = 3_600     # 1 hour
WEB_LEAD_MEDIAN_MAX_S = 172_800   # 2 days

# API during rough patch (weeks_ago 9–12 in seed): cycle params are 168–240 hours.
# In a 90-day window this historical data is present, so we expect at least one
# week with median > 3 days.
API_ROUGH_PATCH_THRESHOLD_S = 3 * 24 * 3_600  # 3 days


# ── Helpers ───────────────────────────────────────────────────────────────────


def unified(client: httpx.Client, repo_id: str, window: int = 30) -> dict:
    r = client.get("/api/metrics/unified", params={"repo_id": repo_id, "window": window})
    assert r.status_code == 200, f"unified endpoint failed: {r.text}"
    return r.json()


# ── Infrastructure ────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_returns_200(self, client: httpx.Client) -> None:
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_health_body(self, client: httpx.Client) -> None:
        r = client.get("/api/health")
        body = r.json()
        assert body.get("status") == "ok"


# ── Repos ─────────────────────────────────────────────────────────────────────


class TestRepos:
    def test_exactly_two_demo_repos(self, client: httpx.Client) -> None:
        r = client.get("/api/repos")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2, f"expected 2 repos, got {data['total']}"

    def test_repo_names(self, client: httpx.Client) -> None:
        r = client.get("/api/repos")
        names = {item["full_name"] for item in r.json()["items"]}
        assert names == {"acme-corp/web", "acme-corp/api"}


# ── Environments ──────────────────────────────────────────────────────────────


class TestEnvironments:
    def test_web_has_production_env(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get("/api/environments", params={"repo_id": web_repo_id})
        assert r.status_code == 200
        prod_envs = [e for e in r.json()["items"] if e["is_production"]]
        assert len(prod_envs) >= 1, "web repo has no production environment"

    def test_api_has_production_env(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        r = client.get("/api/environments", params={"repo_id": api_repo_id})
        assert r.status_code == 200
        prod_envs = [e for e in r.json()["items"] if e["is_production"]]
        assert len(prod_envs) >= 1, "api repo has no production environment"


# ── Open PRs ──────────────────────────────────────────────────────────────────
# These counts are exact: the seed injects a fixed list of open PR specs.
# total/live/draft are immutable once seeded.


class TestOpenPRs:
    def test_web_open_pr_total(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get("/api/metrics/open-prs", params={"repo_id": web_repo_id})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == WEB_OPEN_TOTAL, (
            f"web open PRs: expected total={WEB_OPEN_TOTAL}, got {data['total']}"
        )

    def test_web_open_pr_live_draft_split(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get("/api/metrics/open-prs", params={"repo_id": web_repo_id})
        data = r.json()
        assert data["live"] == WEB_OPEN_LIVE, (
            f"web live PRs: expected {WEB_OPEN_LIVE}, got {data['live']}"
        )
        assert data["draft"] == WEB_OPEN_DRAFT, (
            f"web draft PRs: expected {WEB_OPEN_DRAFT}, got {data['draft']}"
        )

    def test_api_open_pr_total(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        r = client.get("/api/metrics/open-prs", params={"repo_id": api_repo_id})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == API_OPEN_TOTAL, (
            f"api open PRs: expected total={API_OPEN_TOTAL}, got {data['total']}"
        )

    def test_api_open_pr_live_draft_split(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        r = client.get("/api/metrics/open-prs", params={"repo_id": api_repo_id})
        data = r.json()
        assert data["live"] == API_OPEN_LIVE, (
            f"api live PRs: expected {API_OPEN_LIVE}, got {data['live']}"
        )
        assert data["draft"] == API_OPEN_DRAFT, (
            f"api draft PRs: expected {API_OPEN_DRAFT}, got {data['draft']}"
        )


# ── PR Ageing ─────────────────────────────────────────────────────────────────
# Bucket totals are stable (= total open PR counts). Individual bucket counts
# can drift by ±1 near bucket boundaries as calendar time advances, so we
# allow a small tolerance on per-bucket assertions.


class TestPRAgeing:
    def _bucket_map(
        self, client: httpx.Client, repo_id: str
    ) -> dict[str, int]:
        r = client.get("/api/metrics/pr-ageing", params={"repo_id": repo_id})
        assert r.status_code == 200
        return {b["bucket"]: b["count"] for b in r.json()["buckets"]}

    def test_web_ageing_four_buckets(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        buckets = self._bucket_map(client, web_repo_id)
        assert set(buckets.keys()) == {"<2d", "2-7d", "7-14d", ">14d"}, (
            f"unexpected bucket keys: {set(buckets.keys())}"
        )

    def test_web_ageing_total_matches_open_prs(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        buckets = self._bucket_map(client, web_repo_id)
        total = sum(buckets.values())
        assert total == WEB_OPEN_TOTAL, (
            f"web ageing total={total}, expected {WEB_OPEN_TOTAL}"
        )

    def test_web_ageing_bucket_counts(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        """Each bucket count should be within ±1 of the seeded value."""
        buckets = self._bucket_map(client, web_repo_id)
        for bucket, expected in WEB_AGEING.items():
            actual = buckets.get(bucket, 0)
            assert abs(actual - expected) <= 1, (
                f"web ageing bucket '{bucket}': expected ~{expected}, got {actual}"
            )

    def test_api_ageing_four_buckets(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        buckets = self._bucket_map(client, api_repo_id)
        assert set(buckets.keys()) == {"<2d", "2-7d", "7-14d", ">14d"}

    def test_api_ageing_total_matches_open_prs(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        buckets = self._bucket_map(client, api_repo_id)
        total = sum(buckets.values())
        assert total == API_OPEN_TOTAL, (
            f"api ageing total={total}, expected {API_OPEN_TOTAL}"
        )

    def test_api_ageing_bucket_counts(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        buckets = self._bucket_map(client, api_repo_id)
        for bucket, expected in API_AGEING.items():
            actual = buckets.get(bucket, 0)
            assert abs(actual - expected) <= 1, (
                f"api ageing bucket '{bucket}': expected ~{expected}, got {actual}"
            )


# ── Deployment Frequency ──────────────────────────────────────────────────────


class TestDeploymentFrequency:
    def test_web_30d_status_ok(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get(
            "/api/metrics/deployment-frequency",
            params={"repo_id": web_repo_id, "days": 30},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_web_30d_total_in_range(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get(
            "/api/metrics/deployment-frequency",
            params={"repo_id": web_repo_id, "days": 30},
        )
        total = r.json()["total"]
        assert WEB_DEPLOYS_30D_MIN <= total <= WEB_DEPLOYS_30D_MAX, (
            f"web 30d deploys={total}, expected {WEB_DEPLOYS_30D_MIN}–{WEB_DEPLOYS_30D_MAX}"
        )

    def test_web_30d_has_daily_counts(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get(
            "/api/metrics/deployment-frequency",
            params={"repo_id": web_repo_id, "days": 30},
        )
        data = r.json()
        assert data["daily_counts"], "web 30d daily_counts is empty"
        assert len(data["daily_counts"]) <= 30

    def test_web_90d_total_in_range(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get(
            "/api/metrics/deployment-frequency",
            params={"repo_id": web_repo_id, "days": 90},
        )
        total = r.json()["total"]
        assert WEB_DEPLOYS_90D_MIN <= total <= WEB_DEPLOYS_90D_MAX, (
            f"web 90d deploys={total}, expected {WEB_DEPLOYS_90D_MIN}–{WEB_DEPLOYS_90D_MAX}"
        )

    def test_api_has_deployments(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        """API repo should have deployments over the full 90-day window."""
        r = client.get(
            "/api/metrics/deployment-frequency",
            params={"repo_id": api_repo_id, "days": 90},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["total"] > 0


# ── Lead Time ─────────────────────────────────────────────────────────────────


class TestLeadTime:
    def test_web_lead_time_status_ok(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get(
            "/api/metrics/lead-time",
            params={"repo_id": web_repo_id, "days": 30},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_web_lead_time_has_weekly_data(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get(
            "/api/metrics/lead-time",
            params={"repo_id": web_repo_id, "days": 30},
        )
        weekly = r.json()["weekly"]
        assert weekly, "web lead time weekly data is empty"

    def test_web_lead_time_median_in_range(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        """Web team is healthy — lead time should be hours to ~2 days."""
        r = client.get(
            "/api/metrics/lead-time",
            params={"repo_id": web_repo_id, "days": 30},
        )
        medians = [w["median_seconds"] for w in r.json()["weekly"]]
        avg_median = sum(medians) / len(medians)
        assert WEB_LEAD_MEDIAN_MIN_S <= avg_median <= WEB_LEAD_MEDIAN_MAX_S, (
            f"web avg lead time median={avg_median:.0f}s, "
            f"expected {WEB_LEAD_MEDIAN_MIN_S}–{WEB_LEAD_MEDIAN_MAX_S}s"
        )

    def test_web_lead_time_coverage_positive(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        r = client.get(
            "/api/metrics/lead-time",
            params={"repo_id": web_repo_id, "days": 30},
        )
        coverage = r.json()["coverage_percent"]
        assert coverage is not None and coverage > 0, (
            f"web lead time coverage_percent={coverage}"
        )

    def test_api_lead_time_has_data_90d(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        r = client.get(
            "/api/metrics/lead-time",
            params={"repo_id": api_repo_id, "days": 90},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["weekly"], "api 90d lead time weekly data is empty"


# ── PR Cycle Time ─────────────────────────────────────────────────────────────


class TestPRCycleTime:
    def _get_cycle_time(
        self, client: httpx.Client, repo_id: str, days: int = 30
    ) -> dict:
        r = client.get(
            "/api/metrics/pr-cycle-time",
            params={"repo_id": repo_id, "days": days},
        )
        assert r.status_code == 200
        return r.json()

    def test_web_cycle_time_status_ok(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = self._get_cycle_time(client, web_repo_id)
        assert data["status"] == "ok"

    def test_web_cycle_time_has_weekly_data(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = self._get_cycle_time(client, web_repo_id)
        assert data["weekly"], "web cycle time weekly data is empty"

    def test_web_cycle_time_median_reflects_healthy_team(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        """Web team seed params: cycle_hours 4–8. Median should stay in that band."""
        data = self._get_cycle_time(client, web_repo_id, days=30)
        medians = [w["median_seconds"] for w in data["weekly"]]
        avg_median = sum(medians) / len(medians)
        assert WEB_CYCLE_MEDIAN_MIN_S <= avg_median <= WEB_CYCLE_MEDIAN_MAX_S, (
            f"web avg cycle time median={avg_median:.0f}s, "
            f"expected {WEB_CYCLE_MEDIAN_MIN_S}–{WEB_CYCLE_MEDIAN_MAX_S}s"
        )

    def test_web_p75_not_less_than_median(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = self._get_cycle_time(client, web_repo_id)
        for week in data["weekly"]:
            assert week["p75_seconds"] >= week["median_seconds"], (
                f"p75 < median for week {week['week_start']}"
            )

    def test_api_cycle_time_90d_shows_rough_patch(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        """The 90-day window covers the API's rough-patch phase (weeks 9–12).
        At least one week should have a median > 3 days, confirming the story
        arc is present in the data.
        """
        data = self._get_cycle_time(client, api_repo_id, days=90)
        assert data["status"] == "ok"
        weekly = data["weekly"]
        assert weekly, "api 90d cycle time has no weekly data"
        max_median = max(w["median_seconds"] for w in weekly)
        assert max_median > API_ROUGH_PATCH_THRESHOLD_S, (
            f"api 90d max weekly median={max_median:.0f}s; "
            f"expected >={API_ROUGH_PATCH_THRESHOLD_S}s to confirm rough-patch data"
        )

    def test_api_cycle_time_30d_lower_than_90d_max(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        """Recent 30-day window should only include recovery/healthy phases,
        so its median should be well below the rough-patch peak seen in 90d.
        """
        data_30 = self._get_cycle_time(client, api_repo_id, days=30)
        data_90 = self._get_cycle_time(client, api_repo_id, days=90)
        if not data_30["weekly"] or not data_90["weekly"]:
            pytest.skip("insufficient data to compare 30d vs 90d")
        avg_30d = sum(w["median_seconds"] for w in data_30["weekly"]) / len(
            data_30["weekly"]
        )
        max_90d = max(w["median_seconds"] for w in data_90["weekly"])
        assert avg_30d < max_90d, (
            f"30d avg ({avg_30d:.0f}s) should be < 90d peak ({max_90d:.0f}s)"
        )


# ── Unified Dashboard ─────────────────────────────────────────────────────────


class TestUnifiedDashboard:
    def test_web_unified_has_all_sections(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = unified(client, web_repo_id)
        required = {
            "deployment_frequency",
            "lead_time",
            "pr_cycle_time",
            "throughput",
            "open_prs",
            "pr_ageing",
            "data_quality",
        }
        assert required.issubset(data.keys()), (
            f"missing sections: {required - data.keys()}"
        )

    def test_web_unified_metrics_not_setup_required(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = unified(client, web_repo_id)
        assert data["deployment_frequency"]["status"] == "ok"
        assert data["lead_time"]["status"] == "ok"
        assert data["pr_cycle_time"]["status"] == "ok"

    def test_web_unified_open_prs_exact(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = unified(client, web_repo_id)
        open_prs = data["open_prs"]
        assert open_prs["total"] == WEB_OPEN_TOTAL
        assert open_prs["live"] == WEB_OPEN_LIVE
        assert open_prs["draft"] == WEB_OPEN_DRAFT

    def test_web_unified_pr_ageing_total(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = unified(client, web_repo_id)
        bucket_total = sum(b["count"] for b in data["pr_ageing"]["buckets"])
        assert bucket_total == WEB_OPEN_TOTAL

    def test_web_unified_throughput_has_data(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = unified(client, web_repo_id)
        assert data["throughput"]["weekly"], "web unified throughput weekly is empty"

    def test_web_unified_data_quality_has_production_env(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data = unified(client, web_repo_id)
        setup = data["data_quality"]["setup"]
        assert setup["has_production_environment"] is True
        assert "production" in setup["production_environments"]

    def test_api_unified_open_prs_exact(
        self, client: httpx.Client, api_repo_id: str
    ) -> None:
        data = unified(client, api_repo_id)
        open_prs = data["open_prs"]
        assert open_prs["total"] == API_OPEN_TOTAL
        assert open_prs["live"] == API_OPEN_LIVE
        assert open_prs["draft"] == API_OPEN_DRAFT

    def test_window_7d_returns_fewer_deploys_than_90d(
        self, client: httpx.Client, web_repo_id: str
    ) -> None:
        data_7 = unified(client, web_repo_id, window=7)
        data_90 = unified(client, web_repo_id, window=90)
        total_7 = data_7["deployment_frequency"]["total"] or 0
        total_90 = data_90["deployment_frequency"]["total"] or 0
        assert total_7 <= total_90, (
            f"7d deploys ({total_7}) should be <= 90d deploys ({total_90})"
        )
