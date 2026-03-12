# Data Quality

**Goal:** Expose detection health and metrics freshness as service-layer domain logic. Endpoint exposure deferred to PRD 010 (dashboard API).

**Scope:** Three isolated service functions. No schemas, no endpoints, no new models or migrations.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest

---

## Design

### Functions

Three pure query functions in a new `data_quality_service.py`:

#### 1. `get_metrics_freshness(tenant_id, repo_id, session) → MetricsFreshness`

Queries `MetricsRefreshLog` for `max(completed_at)` where `status='success'`.

Returns a dataclass:
```python
@dataclass
class MetricsFreshness:
    status: str           # "ok" | "stale" | "no_data"
    last_refresh_at: datetime | None
```

Rules:
- No rows → `status="no_data"`, `last_refresh_at=None`
- `completed_at` > 2h ago → `status="stale"`
- Otherwise → `status="ok"`
- Boundary: exactly 2h is "ok" (stale is strictly >2h)

#### 2. `get_production_environments(tenant_id, repo_id, session) → list[str]`

Queries `Environment` where `is_production=True`. Returns list of environment names.

#### 3. `get_attribution_coverage(tenant_id, repo_id, default_branch, session, days=30) → float | None`

Counts merged PRs vs attributed PRs in the window (same logic as lead-time route lines 189-221). Returns `round((attributed / total) * 100, 1)` or `None` if no merged PRs.

### Why isolated functions?

Deployment count (30d) already exists via `compute_deployment_frequency` / the deployment-frequency endpoint. We don't duplicate it here. PRD 010 will collate these into a single dashboard response.

### Not included

- Response schemas (deferred to PRD 010)
- API endpoints (deferred to PRD 010)
- Deployment count (already exists)
- New models or migrations

---

## Implementation Plan

### Task 1: Tests for data quality service (RED)

**Files:**
- Create: `server/tests/test_data_quality_service.py`

- [x] **Step 1: Write freshness tests**

Four tests:
- `test_freshness_returns_no_data_when_no_records` — no rows → `no_data`
- `test_freshness_returns_ok_when_recent` — refresh 30m ago → `ok`
- `test_freshness_returns_stale_when_old` — refresh 3h ago → `stale`
- `test_freshness_boundary_exactly_2h_is_ok` — exactly 2h → `ok`

- [x] **Step 2: Write production environments tests**

Two tests:
- `test_production_envs_returns_names` — 2 envs → `["production", "staging-prod"]`
- `test_production_envs_returns_empty_when_none` — no envs → `[]`

- [x] **Step 3: Write attribution coverage tests**

Three tests:
- `test_attribution_coverage_computes_percentage` — 3/10 → `30.0`
- `test_attribution_coverage_returns_none_when_no_prs` — 0 PRs → `None`
- `test_attribution_coverage_100_percent` — 5/5 → `100.0`

- [x] **Step 4: Run tests, verify all fail**

```bash
cd server && python -m pytest tests/test_data_quality_service.py -v
```

- [x] **Step 5: Commit failing tests**

---

### Task 2: Implement data quality service (GREEN)

**Files:**
- Create: `server/app/services/data_quality_service.py`

- [x] **Step 1: Implement `get_metrics_freshness`**

Query `select(func.max(MetricsRefreshLog.completed_at))` filtered by tenant/repo and `status='success'`. Compare to `datetime.now(utc)` with 2h threshold.

- [x] **Step 2: Implement `get_production_environments`**

Query `select(Environment)` filtered by tenant/repo and `is_production=True`. Return `[env.name for env in envs]`.

- [x] **Step 3: Implement `get_attribution_coverage`**

Extract the coverage logic from `routes/metrics.py:189-221` into this function. Two count queries: total merged PRs, attributed PRs.

- [x] **Step 4: Run tests, verify all pass**

```bash
cd server && python -m pytest tests/test_data_quality_service.py -v
```

- [x] **Step 5: Run full test suite**

```bash
cd server && python -m pytest -v
```

- [x] **Step 6: Commit**

---

### Task 3: Update docs

- [x] **Step 1: Update PRD 009 or this RFC with review notes**
- [x] **Step 2: Update server README if needed**
- [x] **Step 3: Commit docs**

---

## Review

- [x] 9 new tests, all passing (103 total)
- [x] `get_metrics_freshness` — boundary test caught `>` vs `>=` bug, fixed with injectable `now` param
- [x] `get_production_environments` — simple query, returns env names
- [x] `get_attribution_coverage` — extracted from lead-time route, reuses same query pattern
- [x] No new endpoints or schemas (deferred to PRD 010)
- [x] No deployment count duplication (already exists in deployment-frequency endpoint)
