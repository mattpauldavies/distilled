# Lead Time Endpoint

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface pre-computed lead time percentiles via a read endpoint with inline attribution coverage.

**Architecture:** Mirrors the deployment-frequency endpoint exactly. Reads from `lead_time_weekly_metrics` (already populated by RFC 005 scheduled recompute). Coverage % computed on-the-fly via two COUNT queries against `pull_requests` and `deployment_attributions`.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest

---

## Design

### Endpoint

`GET /api/metrics/lead-time?repo_id=<uuid>&days=30`

Auth: tenant middleware (same as deployment-frequency).

### Response Schema

```python
class WeeklyLeadTime(BaseModel):
    week_start: date
    median_seconds: float
    p75_seconds: float
    sample_size: int

class LeadTimeResponse(BaseModel):
    status: str                              # "ok" | "setup_required"
    message: str | None = None
    days: int | None = None
    coverage_percent: float | None = None    # attributed / total merged PRs in window
    weekly: list[WeeklyLeadTime] | None = None
```

### Coverage Computation (on-the-fly)

Two COUNT queries at request time:

1. Total merged PRs in window targeting default_branch
2. Of those, how many have at least one `DeploymentAttribution`

`coverage_percent = (attributed / total) * 100` if total > 0, else `None`.

### Response States

| State              | Condition                            |
| ------------------ | ------------------------------------ |
| `setup_required`   | No production environment configured |
| `ok`, empty weekly | Prod env exists, no lead time data   |
| `ok`, with data    | Normal response                      |

---

## Implementation Plan

### Task 1: Schema

**Files:**

- Modify: `server/app/schemas/metrics.py`

- [ ] **Step 1: Add WeeklyLeadTime and LeadTimeResponse schemas**

```python
class WeeklyLeadTime(BaseModel):
    week_start: date
    median_seconds: float
    p75_seconds: float
    sample_size: int


class LeadTimeResponse(BaseModel):
    status: str
    message: str | None = None
    days: int | None = None
    coverage_percent: float | None = None
    weekly: list[WeeklyLeadTime] | None = None
```

- [ ] **Step 2: Commit**

```bash
git add server/app/schemas/metrics.py
git commit -m "add lead time response schemas"
```

---

### Task 2: Route — tests first

**Files:**

- Create: `server/tests/test_lead_time.py`

- [ ] **Step 1: Write test for lead time returns weekly data**

```python
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import TENANT_ID, REPO_ID, make_environment


def _make_weekly_metric(week_start: date, median: float, p75: float, sample: int):
    m = MagicMock()
    m.week_start = week_start
    m.median_seconds = median
    m.p75_seconds = p75
    m.sample_size = sample
    return m


@pytest.mark.asyncio
async def test_lead_time_returns_weekly_data(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True)
    m1 = _make_weekly_metric(date(2025, 1, 13), 3600.0, 7200.0, 5)
    m2 = _make_weekly_metric(date(2025, 1, 6), 1800.0, 3600.0, 3)

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [m1, m2]
    metrics_result.scalars.return_value = scalars_mock

    total_prs_result = MagicMock()
    total_prs_result.scalar_one.return_value = 10

    attributed_prs_result = MagicMock()
    attributed_prs_result.scalar_one.return_value = 8

    mock_session.execute = AsyncMock(
        side_effect=[env_result, metrics_result, total_prs_result, attributed_prs_result]
    )

    resp = await client.get(f"/api/metrics/lead-time?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["days"] == 30
    assert data["coverage_percent"] == 80.0
    assert len(data["weekly"]) == 2
    assert data["weekly"][0]["week_start"] == "2025-01-13"
    assert data["weekly"][0]["median_seconds"] == 3600.0
    assert data["weekly"][0]["p75_seconds"] == 7200.0
    assert data["weekly"][0]["sample_size"] == 5
```

- [ ] **Step 2: Write test for setup_required state**

```python
@pytest.mark.asyncio
async def test_lead_time_setup_required(client, mock_session):
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=env_result)

    resp = await client.get(f"/api/metrics/lead-time?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "setup_required"
    assert data["weekly"] is None
```

- [ ] **Step 3: Write test for zero state**

```python
@pytest.mark.asyncio
async def test_lead_time_zero_state(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True)
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    metrics_result.scalars.return_value = scalars_mock

    total_prs_result = MagicMock()
    total_prs_result.scalar_one.return_value = 0

    attributed_prs_result = MagicMock()
    attributed_prs_result.scalar_one.return_value = 0

    mock_session.execute = AsyncMock(
        side_effect=[env_result, metrics_result, total_prs_result, attributed_prs_result]
    )

    resp = await client.get(f"/api/metrics/lead-time?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["weekly"] == []
    assert data["coverage_percent"] is None
```

- [ ] **Step 4: Write test for custom days and invalid days**

```python
@pytest.mark.asyncio
async def test_lead_time_custom_days(client, mock_session):
    env = make_environment(repo_id=REPO_ID, is_production=True)
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env

    metrics_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    metrics_result.scalars.return_value = scalars_mock

    total_prs_result = MagicMock()
    total_prs_result.scalar_one.return_value = 0

    attributed_prs_result = MagicMock()
    attributed_prs_result.scalar_one.return_value = 0

    mock_session.execute = AsyncMock(
        side_effect=[env_result, metrics_result, total_prs_result, attributed_prs_result]
    )

    resp = await client.get(f"/api/metrics/lead-time?repo_id={REPO_ID}&days=90")

    assert resp.status_code == 200
    assert resp.json()["days"] == 90


@pytest.mark.asyncio
async def test_lead_time_rejects_invalid_days(client, mock_session):
    resp = await client.get(f"/api/metrics/lead-time?repo_id={REPO_ID}&days=45")
    assert resp.status_code == 422
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_lead_time.py -v`
Expected: FAIL (endpoint doesn't exist yet)

- [ ] **Step 6: Commit tests**

```bash
git add server/tests/test_lead_time.py
git commit -m "add lead time endpoint tests"
```

---

### Task 3: Route — implementation

**Files:**

- Modify: `server/app/routes/metrics.py`

- [ ] **Step 1: Add imports and lead-time endpoint**

Add to imports at top of `server/app/routes/metrics.py`:

```python
from sqlalchemy import func
from app.models.deployment_attribution import DeploymentAttribution
from app.models.pull_request import PullRequest
from app.models.metrics import DeploymentDailyMetric, LeadTimeWeeklyMetric, MetricsRefreshLog
from app.schemas.metrics import DailyCount, DeploymentFrequencyResponse, LeadTimeResponse, WeeklyLeadTime
```

Add endpoint after `get_deployment_frequency`:

```python
@router.get("/lead-time")
async def get_lead_time(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    days: DaysWindow = Query(DaysWindow.THIRTY),
) -> LeadTimeResponse:
    # Check for production environment
    env_result = await session.execute(
        select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.repo_id == repo.id,
            Environment.is_production.is_(True),
        ).limit(1)
    )
    if not env_result.scalar_one_or_none():
        return LeadTimeResponse(
            status="setup_required",
            message="no production environment configured",
        )

    since = date.today() - timedelta(days=int(days))
    result = await session.execute(
        select(LeadTimeWeeklyMetric).where(
            LeadTimeWeeklyMetric.tenant_id == tenant_id,
            LeadTimeWeeklyMetric.repo_id == repo.id,
            LeadTimeWeeklyMetric.week_start >= since,
        ).order_by(LeadTimeWeeklyMetric.week_start.desc())
    )
    metrics = result.scalars().all()

    weekly = [
        WeeklyLeadTime(
            week_start=m.week_start,
            median_seconds=m.median_seconds,
            p75_seconds=m.p75_seconds,
            sample_size=m.sample_size,
        )
        for m in metrics
    ]

    # Coverage: attributed PRs / total merged PRs in window
    since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)

    total_prs_result = await session.execute(
        select(func.count()).select_from(
            select(PullRequest.id).where(
                PullRequest.tenant_id == tenant_id,
                PullRequest.repo_id == repo.id,
                PullRequest.base_ref == repo.default_branch,
                PullRequest.merged_at >= since_dt,
            ).subquery()
        )
    )
    total_prs = total_prs_result.scalar_one()

    attributed_result = await session.execute(
        select(func.count()).select_from(
            select(PullRequest.id).where(
                PullRequest.tenant_id == tenant_id,
                PullRequest.repo_id == repo.id,
                PullRequest.base_ref == repo.default_branch,
                PullRequest.merged_at >= since_dt,
                PullRequest.id.in_(select(DeploymentAttribution.pr_id)),
            ).subquery()
        )
    )
    attributed_prs = attributed_result.scalar_one()

    coverage = round((attributed_prs / total_prs) * 100, 1) if total_prs > 0 else None

    return LeadTimeResponse(
        status="ok",
        days=int(days),
        coverage_percent=coverage,
        weekly=weekly,
    )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/test_lead_time.py -v`
Expected: all 5 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd server && python -m pytest -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/app/routes/metrics.py server/app/schemas/metrics.py
git commit -m "add lead time endpoint"
```

---

### Task 4: Documentation

**Files:**

- Modify: `docs/rfcs/007-lead-time-endpoint.md` (add review section)
- Modify: `README.md`, `server/README.md` (if metrics endpoints are listed)

- [ ] **Step 1: Update docs as needed**
- [ ] **Step 2: Commit**

```bash
git commit -m "update docs for lead time endpoint"
```
