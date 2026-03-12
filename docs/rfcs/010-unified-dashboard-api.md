# RFC 010: Unified Dashboard API

**PRD:** `docs/prds/010 - Unified Dashboard API.md`
**Branch:** `feat/dashboard-api`

---

## Summary

Single endpoint that returns everything the dashboard needs in one request. Consolidates 4 scheduled metrics, 2 live metrics, and 3 data quality signals. All queries are sequential on a single session — aggregate table reads are indexed so <400ms is achievable without concurrency.

---

## Endpoint

```http
GET /api/metrics/unified?repo={id}&window=30d
```

- Auth: tenant middleware (existing `get_tenant_id` + `get_verified_repo`)
- `window`: `DaysWindow` enum — `30`, `60`, `90` (default `30`). Moved from `routes/metrics.py` to `schemas/metrics.py` as part of this RFC.
- Repo-scoped

---

## Response Shape

```json
{
  "deployment_frequency": {
    "status": "ok | setup_required",
    "total": 42,
    "days": 30,
    "daily_counts": [{ "date": "2026-03-11", "count": 3 }]
  },
  "lead_time": {
    "status": "ok | setup_required",
    "weekly": [
      {
        "week_start": "2026-03-03",
        "median_seconds": 3600.0,
        "p75_seconds": 7200.0,
        "sample_size": 5
      }
    ]
  },
  "pr_cycle_time": {
    "status": "ok | setup_required",
    "weekly": [
      {
        "week_start": "2026-03-03",
        "median_seconds": 1800.0,
        "p75_seconds": 3600.0,
        "sample_size": 8
      }
    ]
  },
  "throughput": {
    "weekly": [{ "week_start": "2026-03-03", "pr_count": 12 }]
  },
  "open_prs": { "total": 5, "live": 3, "draft": 2 },
  "pr_ageing": {
    "buckets": [
      { "bucket": "<2d", "count": 2 },
      { "bucket": "2-7d", "count": 1 }
    ]
  },
  "data_quality": {
    "attribution_coverage_percent": 87.5,
    "freshness": {
      "status": "ok | stale | no_data",
      "last_refresh_at": "2026-03-12T10:00:00Z"
    },
    "setup": {
      "has_production_environment": true,
      "production_environments": ["production"]
    }
  }
}
```

**Notes:**

- `deployment_frequency`, `lead_time`, `pr_cycle_time` return `"status": "setup_required"` with null data fields when no production environment exists
- `throughput`, `open_prs`, `pr_ageing` don't require prod env — always return data. `throughput` has no `status` field (it never fails).
- `data_quality.freshness.last_refresh_at` is `null` when status is `no_data`
- `data_quality.attribution_coverage_percent` is `null` when no merged PRs exist in window

---

## Architecture

### Service layer refactor

Query functions live in their **domain services** (not a single god service). The dashboard service is a thin orchestrator only.

#### `metrics_service.py` — aggregate metric reads (added alongside existing compute functions)

| Function                                                    | Source                                           | What it does                                                                                                                     |
| ----------------------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `get_deployment_frequency(tenant_id, repo, session, days)`  | Currently inline in `routes/metrics.py` L103-137 | Reads `DeploymentDailyMetric` aggregate table, returns dict with `total` + `daily_counts`                                        |
| `get_lead_time_summary(tenant_id, repo, session, days)`     | Currently inline in `routes/metrics.py` L140-212 | Reads `LeadTimeWeeklyMetric`, returns list of weekly percentiles. **No attribution coverage** — that's in `data_quality` section |
| `get_pr_cycle_time_summary(tenant_id, repo, session, days)` | New — same shape as lead time                    | Reads `PRCycleTimeWeeklyMetric`, returns list of weekly percentiles                                                              |
| `get_pr_throughput(tenant_id, repo, session, days)`         | New                                              | Reads `PRThroughputWeeklyMetric`, returns list of weekly counts                                                                  |

#### `pull_request_service.py` — **new** live PR queries

| Function                                                    | Source                                           | What it does                                                                                                                     |
| ----------------------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `get_open_pr_count(tenant_id, repo, session)`               | Currently inline in `routes/metrics.py` L215-239 | Counts open PRs by draft status                                                                                                  |
| `get_pr_ageing(tenant_id, repo, session)`                   | Currently inline in `routes/metrics.py` L242-273 | Groups open PRs into age buckets                                                                                                 |

#### `dashboard_service.py` — thin orchestrator only

Calls domain services (`metrics_service`, `pull_request_service`, `data_quality_service`, `environment_service`), assembles `UnifiedDashboardResponse`. Contains **no queries** of its own.

Each query function returns plain data (dicts/lists), not Pydantic models. The orchestrator and route handlers handle schema construction.

#### PR ageing bucket DRY

Extract the SQL `case` expression into a helper in `pull_request_service.py`:

```python
def _ageing_bucket_expr():
    now = func.now()
    age = now - PullRequest.opened_at
    return sa.case(
        (age < sa.text("interval '2 days'"), sa.literal("<2d")),
        (age < sa.text("interval '7 days'"), sa.literal("2-7d")),
        (age < sa.text("interval '14 days'"), sa.literal("7-14d")),
        else_=sa.literal(">14d"),
    ).label("bucket")
```

Used by `get_pr_ageing` — single definition, no duplication.

#### Attribution coverage DRY

The lead-time route currently computes attribution coverage inline (L173-205). This duplicates `data_quality_service.get_attribution_coverage`. After refactor:

- `get_lead_time_summary` returns only percentile data (no coverage)
- The standalone `/lead-time` route calls both `get_lead_time_summary` + `data_quality_service.get_attribution_coverage` to preserve its existing response shape
- The unified endpoint gets coverage from `data_quality_service.get_attribution_coverage` (in the `data_quality` section)

**Subtle behavior change:** The inline version used `date.today()` (local midnight) while the service uses `datetime.now(timezone.utc)` (current UTC time). The service version is more correct — both callers will use it going forward.

#### Unified orchestrator

```python
async def get_unified_dashboard(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
    days: int = 30,
) -> UnifiedDashboardResponse:
    # Single query — derive has_prod from result
    prod_envs = await get_production_environments(tenant_id, repo.id, session)
    has_prod = len(prod_envs) > 0

    # Scheduled metrics — prod-dependent ones short-circuit
    if has_prod:
        dep_freq = await get_deployment_frequency(tenant_id, repo, session, days)
        lead_time = await get_lead_time_summary(tenant_id, repo, session, days)
        cycle_time = await get_pr_cycle_time_summary(tenant_id, repo, session, days)
    else:
        dep_freq = lead_time = cycle_time = None

    throughput = await get_pr_throughput(tenant_id, repo, session, days)

    # Live metrics
    open_prs = await get_open_pr_count(tenant_id, repo, session)
    ageing = await get_pr_ageing(tenant_id, repo, session)

    # Data quality
    freshness = await get_metrics_freshness(tenant_id, repo.id, session)
    coverage = await get_attribution_coverage(
        tenant_id, repo.id, repo.default_branch, session, days,
    )

    # Assemble response — flat structure, no scheduled/live grouping
    return UnifiedDashboardResponse(
        deployment_frequency=DeploymentFrequencySection(
            status="ok" if has_prod else "setup_required",
            total=dep_freq["total"] if dep_freq else None,
            days=days if dep_freq else None,
            daily_counts=dep_freq["daily_counts"] if dep_freq else None,
        ),
        lead_time=LeadTimeSection(
            status="ok" if has_prod else "setup_required",
            weekly=lead_time if lead_time else None,
        ),
        pr_cycle_time=PRCycleTimeSection(
            status="ok" if has_prod else "setup_required",
            weekly=cycle_time if cycle_time else None,
        ),
        throughput=ThroughputSection(
            weekly=throughput,
        ),
        open_prs=OpenPRsSection(
            total=open_prs["total"],
            live=open_prs["live"],
            draft=open_prs["draft"],
        ),
        pr_ageing=PRAgeingSection(buckets=ageing),
        data_quality=DataQuality(
            attribution_coverage_percent=coverage,
            freshness=FreshnessInfo(
                status=freshness.status,
                last_refresh_at=freshness.last_refresh_at,
            ),
            setup=SetupInfo(
                has_production_environment=has_prod,
                production_environments=prod_envs,
            ),
        ),
    )
```

All queries are sequential on a single `AsyncSession`. Aggregate table reads are indexed — sequential execution is safe and simple. If latency becomes an issue later, we can introduce session-per-query concurrency.

### Existing route refactor

Individual endpoints in `routes/metrics.py` become thin wrappers:

```python
@router.get("/deployment-frequency")
async def get_deployment_frequency_endpoint(...) -> DeploymentFrequencyResponse:
    if not await has_production_environment(tenant_id, repo.id, session):
        return DeploymentFrequencyResponse(status="setup_required", message="no production environment configured")
    result = await dashboard_service.get_deployment_frequency(tenant_id, repo, session, int(days))
    return DeploymentFrequencyResponse(status="ok", total=result["total"], days=int(days), daily_counts=result["daily_counts"])
```

No behavior change. Existing tests updated to patch service functions instead of mocking session queries directly.

### Route registration

New endpoint added to `routes/metrics.py` (alongside existing endpoints):

```python
@router.get("/unified")
async def get_unified_dashboard_endpoint(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    window: DaysWindow = Query(DaysWindow.THIRTY),
) -> UnifiedDashboardResponse:
    return await dashboard_service.get_unified_dashboard(tenant_id, repo, session, int(window))
```

---

## Schemas

New Pydantic models in `schemas/metrics.py`. These are **dedicated types for the unified response** — not reusing individual endpoint response types which carry fields irrelevant to the unified context.

```python
# Shared building blocks (also used by individual endpoints)
class WeeklyPercentiles(BaseModel):
    week_start: date
    median_seconds: float
    p75_seconds: float
    sample_size: int

class WeeklyThroughput(BaseModel):
    week_start: date
    pr_count: int

# Unified response sections
class DeploymentFrequencySection(BaseModel):
    status: str  # "ok" | "setup_required"
    total: int | None = None
    days: int | None = None
    daily_counts: list[DailyCount] | None = None

class LeadTimeSection(BaseModel):
    status: str
    weekly: list[WeeklyPercentiles] | None = None

class PRCycleTimeSection(BaseModel):
    status: str
    weekly: list[WeeklyPercentiles] | None = None

class ThroughputSection(BaseModel):
    weekly: list[WeeklyThroughput] | None = None

class OpenPRsSection(BaseModel):
    total: int
    live: int
    draft: int

class PRAgeingSection(BaseModel):
    buckets: list[AgeBucket]

class FreshnessInfo(BaseModel):
    status: str  # "ok" | "stale" | "no_data"
    last_refresh_at: datetime | None

class SetupInfo(BaseModel):
    has_production_environment: bool
    production_environments: list[str]

class DataQuality(BaseModel):
    attribution_coverage_percent: float | None
    freshness: FreshnessInfo
    setup: SetupInfo

class UnifiedDashboardResponse(BaseModel):
    deployment_frequency: DeploymentFrequencySection
    lead_time: LeadTimeSection
    pr_cycle_time: PRCycleTimeSection
    throughput: ThroughputSection
    open_prs: OpenPRsSection
    pr_ageing: PRAgeingSection
    data_quality: DataQuality
```

`WeeklyLeadTime` (existing) can become an alias for `WeeklyPercentiles` to avoid breaking the standalone lead-time endpoint schema.

---

## What doesn't change

- No new DB tables or migrations
- No caching (MVP per PRD)
- Webhook/recompute pipeline untouched
- Existing individual endpoints stay available (refactored internals, same external behavior)

---

## Files touched

| File                                | Change                                                                                                              |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `services/metrics_service.py`       | Add 4 read-side query functions (deployment freq, lead time, cycle time, throughput)                                |
| `services/pull_request_service.py`  | **New** — `get_open_pr_count`, `get_pr_ageing`, `_ageing_bucket_expr`                                              |
| `services/dashboard_service.py`     | **New** — thin orchestrator calling domain services, assembles `UnifiedDashboardResponse`                           |
| `routes/metrics.py`                 | Add `/unified` endpoint, refactor existing endpoints to call service functions, move `DaysWindow` import to schemas |
| `schemas/metrics.py`                | Add `DaysWindow` enum, unified response models, `WeeklyPercentiles`, `WeeklyThroughput`, etc.                       |
| `services/data_quality_service.py`  | No changes                                                                                                          |
| `tests/test_metrics_service.py`     | Add tests for new read-side query functions                                                                         |
| `tests/test_pull_request_service.py`| **New** — tests for open PR count + PR ageing                                                                      |
| `tests/test_dashboard_service.py`   | **New** — unit tests for orchestrator assembly                                                                      |
| `tests/test_metrics_routes.py`      | Update mocks to patch service functions instead of session queries                                                  |

---

## Testing

- Unit tests for each extracted service function (mock session, verify correct query construction)
- Unit test for `get_unified_dashboard` orchestrator — mock individual service functions, verify full assembly into `UnifiedDashboardResponse` with concrete expected shape
- Route test for `/unified` endpoint (mock service, verify response serialization)
- Existing endpoint tests updated to patch new service layer
- Edge cases: no prod env (setup_required), no data (nulls), no merged PRs (null coverage)

---

## Acceptance criteria (from PRD)

- [x] Single request loads full dashboard → one `GET /unified` call
- [x] Response time acceptable (<400ms target) → indexed aggregate reads, sequential execution
- [x] Repo-scoped → `get_verified_repo` middleware

---

## Implementation Plan

**Goal:** Single endpoint (`GET /api/metrics/unified`) that returns all dashboard data in one request.

**Architecture:** Query functions live in domain services (`metrics_service`, `pull_request_service`, `data_quality_service`). `dashboard_service.py` is a thin orchestrator that calls domain services and assembles the response. Existing routes become thin wrappers calling the same domain services.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest + pytest-asyncio

### File Structure

| File | Responsibility |
|---|---|
| `server/app/schemas/metrics.py` | All metric Pydantic models + `DaysWindow` enum |
| `server/app/services/metrics_service.py` | Existing compute functions + new read-side query functions |
| `server/app/services/pull_request_service.py` | **New** — live PR queries (open count, ageing) |
| `server/app/services/dashboard_service.py` | **New** — thin orchestrator only, no queries |
| `server/app/routes/metrics.py` | Route handlers (thin wrappers) + new `/unified` endpoint |

---

### Task 1: Add schemas

- [x] Add DaysWindow enum and unified response types to `schemas/metrics.py`
- [x] Verify imports, commit

---

### Task 2: Metrics service read functions (TDD)

- [ ] Add tests for `get_deployment_frequency`, `get_lead_time_summary`, `get_pr_cycle_time_summary`, `get_pr_throughput` to `tests/test_metrics_service.py`
- [ ] Implement functions in `services/metrics_service.py`
- [ ] Run full suite, commit

---

### Task 3: Pull request service (TDD)

- [ ] Create `tests/test_pull_request_service.py` with tests for `get_open_pr_count` and `get_pr_ageing`
- [ ] Create `services/pull_request_service.py` with implementations + `_ageing_bucket_expr`
- [ ] Run full suite, commit

---

### Task 4: Dashboard orchestrator (TDD)

- [ ] Create `tests/test_dashboard_service.py` with orchestrator tests (happy path + no prod env)
- [ ] Create `services/dashboard_service.py` — thin orchestrator calling domain services
- [ ] Run full suite, commit

---

### Task 5: Refactor existing routes + add unified endpoint

- [ ] Refactor route handlers to delegate to domain services
- [ ] Add `GET /unified` route + test
- [ ] Run full suite, commit

---

### Task 6: Update documentation

- [ ] Update server README, root README
- [ ] Commit
- [ ] **Step 4: Run full test suite**
- [ ] **Step 5: Commit**

---

### Task 8: Update documentation

**Files:**
- Modify: `server/README.md`, `README.md`

- [ ] **Step 1: Update server README with new endpoint**
- [ ] **Step 2: Update root README if it lists endpoints**
- [ ] **Step 3: Commit docs**

---

### Verification Checklist

- [ ] `cd server && python -m pytest -v` — all tests pass
- [ ] `cd server && python -m pytest --cov=app --cov-report=term-missing` — coverage maintained
- [ ] Existing endpoints still work unchanged
- [ ] No duplicate query definitions
