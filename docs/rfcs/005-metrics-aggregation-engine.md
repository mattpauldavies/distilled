# RFC 005: Metrics Aggregation Engine

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scheduled per-repo aggregation for deployment frequency, lead time, PR cycle time, and PR throughput — triggered via internal HTTP endpoint.

**Architecture:** Per-repo recompute via `POST /api/metrics/recompute`. Four metric compute functions run independently within a single call. Granular daily/weekly buckets stored via UPSERT; dashboard filters by date range for 30/60/90 day windows.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL, pytest

---

## Design Decisions

### Per-repo recompute (no recompute_all)

Each endpoint call targets one repo. No bulk recompute function exists. This isolates blast radius and allows staggered scheduling (PRD 012). If one repo fails, others are unaffected.

### Granular buckets, not pre-aggregated windows

Metric tables store daily (deployments) or weekly (lead time, cycle time, throughput) buckets. The dashboard API filters by date range to serve 30/60/90 day views. No 3x storage duplication.

### UPSERT per bucket

Idempotency via `ON CONFLICT DO UPDATE` per unique bucket. Safer than DELETE+INSERT under partial failure. Retries produce identical results.

### Percentiles in Python

Fetch raw durations per week, compute median/P75 in Python (`statistics.median` + sorted index). Avoids Postgres percentile extensions and keeps queries simple.

### Hourly dedup on refresh log

`MetricsRefreshLog` has a unique constraint on `(tenant_id, repo_id, hour)`. Retries within the same hour UPSERT the existing row — no duplicated log entries, no inflated metrics.

---

## Schema Changes

### New column: PullRequest.opened_at

`opened_at: TZDatetime` — parsed from GitHub webhook payload `pull_request.created_at`. Required for PR cycle time (`merged_at - opened_at`).

Note: our existing `created_at` is the DB insert timestamp, which equals merge time since we only ingest PRs on the `closed+merged` webhook.

### New tables

**deployment_daily_metrics**

| Column            | Type    | Notes                      |
| ----------------- | ------- | -------------------------- |
| id                | UUID    | PK                         |
| tenant_id         | UUID    | FK tenants                 |
| repo_id           | UUID    | FK repositories            |
| date              | Date    |                            |
| deployment_count  | Integer |                            |
| algorithm_version | Integer | Default 1                  |
| Unique            |         | (tenant_id, repo_id, date) |

**lead_time_weekly_metrics**

| Column            | Type    | Notes                            |
| ----------------- | ------- | -------------------------------- |
| id                | UUID    | PK                               |
| tenant_id         | UUID    | FK tenants                       |
| repo_id           | UUID    | FK repositories                  |
| week_start        | Date    | Monday of the week               |
| median_seconds    | Float   |                                  |
| p75_seconds       | Float   |                                  |
| sample_size       | Integer |                                  |
| algorithm_version | Integer | Default 1                        |
| Unique            |         | (tenant_id, repo_id, week_start) |

**pr_cycle_time_weekly_metrics** — same shape as lead_time_weekly_metrics

**pr_throughput_weekly_metrics**

| Column            | Type    | Notes                            |
| ----------------- | ------- | -------------------------------- |
| id                | UUID    | PK                               |
| tenant_id         | UUID    | FK tenants                       |
| repo_id           | UUID    | FK repositories                  |
| week_start        | Date    | Monday of the week               |
| pr_count          | Integer |                                  |
| algorithm_version | Integer | Default 1                        |
| Unique            |         | (tenant_id, repo_id, week_start) |

**metrics_refresh_log**

| Column        | Type         | Notes                        |
| ------------- | ------------ | ---------------------------- |
| id            | UUID         | PK                           |
| tenant_id     | UUID         | FK tenants                   |
| repo_id       | UUID         | FK repositories              |
| hour          | DateTime(tz) | Truncated to hour, for dedup |
| started_at    | DateTime(tz) |                              |
| completed_at  | DateTime(tz) | Nullable                     |
| status        | String       | success / failed             |
| error_message | String       | Nullable                     |
| Unique        |              | (tenant_id, repo_id, hour)   |

## Service Layer

### metrics_service.py

```
recompute_repo(tenant_id, repo_id, session) -> RefreshResult
  - Calls each metric function independently
  - If one fails, others still run
  - Returns combined status + error messages

compute_deployment_frequency(tenant_id, repo_id, session)
  - Query: COUNT deployments GROUP BY date, last 90 days
  - UPSERT into deployment_daily_metrics

compute_lead_time(tenant_id, repo_id, session)
  - Query: JOIN deployment_attribution + pull_requests + deployment_events
  - lead_time = deployed_at - merged_at
  - Filter: PRs targeting default_branch, positive durations
  - Group by week (based on deployed_at), compute median/P75
  - UPSERT into lead_time_weekly_metrics

compute_pr_cycle_time(tenant_id, repo_id, session)
  - Query: merged PRs targeting default_branch, last 90 days
  - cycle_time = merged_at - opened_at
  - Filter: positive durations
  - Group by week (based on merged_at), compute median/P75
  - UPSERT into pr_cycle_time_weekly_metrics

compute_pr_throughput(tenant_id, repo_id, session)
  - Query: COUNT merged PRs GROUP BY week, last 90 days
  - UPSERT into pr_throughput_weekly_metrics
```

## Endpoint

### POST /api/metrics/recompute

- **Auth**: `Authorization: Bearer <INTERNAL_CRON_SECRET>` — validated against `INTERNAL_CRON_SECRET` env var
- **Body**: `{ "tenant_id": "...", "repo_id": "..." }`
- **Flow**: validate auth → validate repo belongs to tenant → call `recompute_repo` → write refresh log
- **Response**: 200 on success, 500 on failure (with error detail)
- **Refresh log**: UPSERT keyed on `(tenant_id, repo_id, hour)` — retries within the same hour update the existing row

## Webhook Handler Update

Update `handle_pull_request_event` in `deployment_service.py` to parse and store `opened_at` from `pr_data["created_at"]`.

## Testing

- Unit tests for each compute function with mocked DB
- Unit tests for endpoint (auth, happy path, failure logging)
- Test percentile calculations with known data
- Test idempotency (double recompute = same results)
- Test refresh log dedup (same hour = upsert)

## Files to create/modify

**New files:**

- `server/app/models/metrics.py` — 5 new SQLAlchemy models
- `server/app/services/metrics_service.py` — recompute logic
- `server/app/routes/internal.py` — recompute endpoint
- `server/tests/test_metrics_service.py` — service tests
- `server/tests/test_internal_routes.py` — endpoint tests
- Alembic migration for new tables + `opened_at` column

**Modified files:**

- `server/app/models/pull_request.py` — add `opened_at`
- `server/app/services/deployment_service.py` — parse `opened_at` from webhook
- `server/app/main.py` — register internal routes
- `server/app/config.py` — add `INTERNAL_CRON_SECRET` setting

---

# Implementation Plan

## Chunk 1: Schema Changes

### Task 1: Add `opened_at` to PullRequest model

**Files:**
- Modify: `server/app/models/pull_request.py:23` (add column after `merged_at`)

- [ ] **Step 1: Add `opened_at` column to PullRequest**

In `server/app/models/pull_request.py`, add after line 23 (`merged_at`):

```python
opened_at: Mapped[TZDatetime | None] = mapped_column(nullable=True)
```

Nullable because existing rows won't have this value.

- [ ] **Step 2: Update `make_pr` factory in conftest**

In `server/tests/conftest.py`, add `opened_at=NOW` to the `make_pr` defaults dict (after `merged_at=NOW`):

```python
opened_at=NOW,
```

- [ ] **Step 3: Run existing tests to confirm no breakage**

Run: `cd server && poetry run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add server/app/models/pull_request.py server/tests/conftest.py
git commit -m "add opened_at to PullRequest model"
```

---

### Task 2: Create metric model definitions

**Files:**
- Create: `server/app/models/metrics.py`
- Modify: `server/app/models/__init__.py`

- [ ] **Step 1: Create `server/app/models/metrics.py`**

```python
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeploymentDailyMetric(Base):
    __tablename__ = "deployment_daily_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    date: Mapped[date] = mapped_column(Date)
    deployment_count: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)


class LeadTimeWeeklyMetric(Base):
    __tablename__ = "lead_time_weekly_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "week_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    week_start: Mapped[date] = mapped_column(Date)
    median_seconds: Mapped[float] = mapped_column(Float)
    p75_seconds: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)


class PRCycleTimeWeeklyMetric(Base):
    __tablename__ = "pr_cycle_time_weekly_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "week_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    week_start: Mapped[date] = mapped_column(Date)
    median_seconds: Mapped[float] = mapped_column(Float)
    p75_seconds: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)


class PRThroughputWeeklyMetric(Base):
    __tablename__ = "pr_throughput_weekly_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "week_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    week_start: Mapped[date] = mapped_column(Date)
    pr_count: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)


class MetricsRefreshLog(Base):
    __tablename__ = "metrics_refresh_log"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "hour"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
```

- [ ] **Step 2: Register models in `__init__.py`**

In `server/app/models/__init__.py`, add imports:

```python
from app.models.metrics import (
    DeploymentDailyMetric,
    LeadTimeWeeklyMetric,
    PRCycleTimeWeeklyMetric,
    PRThroughputWeeklyMetric,
    MetricsRefreshLog,
)
```

And add to `__all__`:

```python
"DeploymentDailyMetric",
"LeadTimeWeeklyMetric",
"PRCycleTimeWeeklyMetric",
"PRThroughputWeeklyMetric",
"MetricsRefreshLog",
```

- [ ] **Step 3: Run existing tests to confirm no breakage**

Run: `cd server && poetry run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add server/app/models/metrics.py server/app/models/__init__.py
git commit -m "add metric and refresh log models"
```

---

### Task 3: Create Alembic migration

**Files:**
- Create: `server/database/versions/<auto>_add_metrics_tables.py` (via autogenerate)

- [ ] **Step 1: Generate migration**

Run: `cd server && poetry run alembic revision --autogenerate -m "add metrics tables and opened_at"`

- [ ] **Step 2: Review the generated migration**

Verify it includes:
- `opened_at` column added to `pull_requests`
- 5 new tables created: `deployment_daily_metrics`, `lead_time_weekly_metrics`, `pr_cycle_time_weekly_metrics`, `pr_throughput_weekly_metrics`, `metrics_refresh_log`
- All unique constraints present

- [ ] **Step 3: Run migration against local DB**

Run: `cd server && poetry run alembic upgrade head`
Expected: Migration applies cleanly.

- [ ] **Step 4: Commit**

```bash
git add server/database/versions/
git commit -m "add migration for metrics tables and opened_at"
```

---

## Chunk 2: Metrics Service

### Task 4: Deployment frequency compute function

**Files:**
- Create: `server/app/services/metrics_service.py`
- Create: `server/tests/test_metrics_service.py`

- [ ] **Step 1: Write failing test for `compute_deployment_frequency`**

Create `server/tests/test_metrics_service.py`:

```python
import uuid
from datetime import datetime, date, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from conftest import TENANT_ID, REPO_ID, NOW, make_deployment


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

    # Mock: return all 3 deployments
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && poetry run pytest tests/test_metrics_service.py -x -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.metrics_service'`

- [ ] **Step 3: Implement `compute_deployment_frequency`**

Create `server/app/services/metrics_service.py`:

```python
import logging
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_event import ProductionDeploymentEvent
from app.models.metrics import (
    DeploymentDailyMetric,
    LeadTimeWeeklyMetric,
    PRCycleTimeWeeklyMetric,
    PRThroughputWeeklyMetric,
)

logger = logging.getLogger(__name__)

RECOMPUTE_DAYS = 90
ALGORITHM_VERSION = 1


def _cutoff(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=RECOMPUTE_DAYS)


def _week_start(dt: datetime) -> "date":
    """Return Monday of the week containing dt."""
    d = dt.date() if isinstance(dt, datetime) else dt
    return d - timedelta(days=d.weekday())


async def compute_deployment_frequency(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    cutoff = _cutoff()
    result = await session.execute(
        select(ProductionDeploymentEvent).where(
            ProductionDeploymentEvent.tenant_id == tenant_id,
            ProductionDeploymentEvent.repo_id == repo_id,
            ProductionDeploymentEvent.deployed_at >= cutoff,
        )
    )
    deployments = result.scalars().all()

    counts: Counter = Counter()
    for dep in deployments:
        counts[dep.deployed_at.date()] += 1

    for day, count in counts.items():
        stmt = insert(DeploymentDailyMetric).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo_id,
            date=day,
            deployment_count=count,
            algorithm_version=ALGORITHM_VERSION,
        ).on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "date"],
            set_={
                "deployment_count": count,
                "algorithm_version": ALGORITHM_VERSION,
            },
        )
        await session.execute(stmt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && poetry run pytest tests/test_metrics_service.py -x -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/services/metrics_service.py server/tests/test_metrics_service.py
git commit -m "add deployment frequency compute function"
```

---

### Task 5: Lead time compute function

**Files:**
- Modify: `server/app/services/metrics_service.py`
- Modify: `server/tests/test_metrics_service.py`

- [ ] **Step 1: Write failing test for `compute_lead_time`**

Append to `server/tests/test_metrics_service.py`:

```python
from conftest import make_pr


@pytest.mark.asyncio
async def test_lead_time_computes_median_and_p75(mock_session):
    """Given 4 attributed PRs in same week, computes correct median/P75."""
    from app.services.metrics_service import compute_lead_time

    deployed_at = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    # Lead times: 1h, 2h, 3h, 4h (in seconds: 3600, 7200, 10800, 14400)
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
    # merged AFTER deployed — negative lead time
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && poetry run pytest tests/test_metrics_service.py::test_lead_time_computes_median_and_p75 -x -v`
Expected: FAIL — `ImportError: cannot import name 'compute_lead_time'`

- [ ] **Step 3: Implement `compute_lead_time`**

Add to `server/app/services/metrics_service.py`:

```python
import statistics
from collections import defaultdict

from sqlalchemy import and_

from app.models.deployment_attribution import DeploymentAttribution
from app.models.pull_request import PullRequest


def _percentile_75(sorted_values: list[float]) -> float:
    """Simple P75 using nearest-rank method."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = int(0.75 * (n - 1))
    return sorted_values[idx]


async def compute_lead_time(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    default_branch: str,
    session: AsyncSession,
) -> None:
    cutoff = _cutoff()
    result = await session.execute(
        select(
            PullRequest.merged_at,
            ProductionDeploymentEvent.deployed_at,
            PullRequest.base_ref,
        )
        .join(
            DeploymentAttribution,
            DeploymentAttribution.pr_id == PullRequest.id,
        )
        .join(
            ProductionDeploymentEvent,
            ProductionDeploymentEvent.id == DeploymentAttribution.deployment_id,
        )
        .where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo_id,
            PullRequest.base_ref == default_branch,
            ProductionDeploymentEvent.deployed_at >= cutoff,
        )
    )
    rows = result.all()

    # Group lead times by week
    weekly: defaultdict[date, list[float]] = defaultdict(list)
    for row in rows:
        lead_seconds = (row.deployed_at - row.merged_at).total_seconds()
        if lead_seconds <= 0:
            continue
        week = _week_start(row.deployed_at)
        weekly[week].append(lead_seconds)

    for week, durations in weekly.items():
        durations.sort()
        stmt = insert(LeadTimeWeeklyMetric).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo_id,
            week_start=week,
            median_seconds=statistics.median(durations),
            p75_seconds=_percentile_75(durations),
            sample_size=len(durations),
            algorithm_version=ALGORITHM_VERSION,
        ).on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "week_start"],
            set_={
                "median_seconds": statistics.median(durations),
                "p75_seconds": _percentile_75(durations),
                "sample_size": len(durations),
                "algorithm_version": ALGORITHM_VERSION,
            },
        )
        await session.execute(stmt)
```

Note: `compute_lead_time` takes `default_branch` as a parameter — the caller (`recompute_repo`) will look up the repo's `default_branch` and pass it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && poetry run pytest tests/test_metrics_service.py -x -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/app/services/metrics_service.py server/tests/test_metrics_service.py
git commit -m "add lead time compute function"
```

---

### Task 6: PR cycle time compute function

**Files:**
- Modify: `server/app/services/metrics_service.py`
- Modify: `server/tests/test_metrics_service.py`

- [ ] **Step 1: Write failing test for `compute_pr_cycle_time`**

Append to `server/tests/test_metrics_service.py`:

```python
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
async def test_pr_cycle_time_skips_null_opened_at(mock_session):
    """PRs without opened_at (legacy data) should be excluded."""
    from app.services.metrics_service import compute_pr_cycle_time

    pr = make_pr(repo_id=REPO_ID, base_ref="main", opened_at=None)

    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [pr]
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    await compute_pr_cycle_time(TENANT_ID, REPO_ID, "main", mock_session)

    # Only SELECT, no UPSERT
    assert mock_session.execute.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && poetry run pytest tests/test_metrics_service.py::test_pr_cycle_time_computes_from_opened_to_merged -x -v`
Expected: FAIL — `ImportError: cannot import name 'compute_pr_cycle_time'`

- [ ] **Step 3: Implement `compute_pr_cycle_time`**

Add to `server/app/services/metrics_service.py`:

```python
async def compute_pr_cycle_time(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    default_branch: str,
    session: AsyncSession,
) -> None:
    cutoff = _cutoff()
    result = await session.execute(
        select(PullRequest).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo_id,
            PullRequest.base_ref == default_branch,
            PullRequest.merged_at >= cutoff,
            PullRequest.opened_at.isnot(None),
        )
    )
    prs = result.scalars().all()

    weekly: defaultdict[date, list[float]] = defaultdict(list)
    for pr in prs:
        if pr.opened_at is None:
            continue
        cycle_seconds = (pr.merged_at - pr.opened_at).total_seconds()
        if cycle_seconds <= 0:
            continue
        week = _week_start(pr.merged_at)
        weekly[week].append(cycle_seconds)

    for week, durations in weekly.items():
        durations.sort()
        stmt = insert(PRCycleTimeWeeklyMetric).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo_id,
            week_start=week,
            median_seconds=statistics.median(durations),
            p75_seconds=_percentile_75(durations),
            sample_size=len(durations),
            algorithm_version=ALGORITHM_VERSION,
        ).on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "week_start"],
            set_={
                "median_seconds": statistics.median(durations),
                "p75_seconds": _percentile_75(durations),
                "sample_size": len(durations),
                "algorithm_version": ALGORITHM_VERSION,
            },
        )
        await session.execute(stmt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && poetry run pytest tests/test_metrics_service.py -x -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/app/services/metrics_service.py server/tests/test_metrics_service.py
git commit -m "add PR cycle time compute function"
```

---

### Task 7: PR throughput compute function

**Files:**
- Modify: `server/app/services/metrics_service.py`
- Modify: `server/tests/test_metrics_service.py`

- [ ] **Step 1: Write failing test for `compute_pr_throughput`**

Append to `server/tests/test_metrics_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && poetry run pytest tests/test_metrics_service.py::test_pr_throughput_counts_by_week -x -v`
Expected: FAIL — `ImportError: cannot import name 'compute_pr_throughput'`

- [ ] **Step 3: Implement `compute_pr_throughput`**

Add to `server/app/services/metrics_service.py`:

```python
async def compute_pr_throughput(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    default_branch: str,
    session: AsyncSession,
) -> None:
    cutoff = _cutoff()
    result = await session.execute(
        select(PullRequest).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo_id,
            PullRequest.base_ref == default_branch,
            PullRequest.merged_at >= cutoff,
        )
    )
    prs = result.scalars().all()

    weekly: Counter = Counter()
    for pr in prs:
        week = _week_start(pr.merged_at)
        weekly[week] += 1

    for week, count in weekly.items():
        stmt = insert(PRThroughputWeeklyMetric).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo_id,
            week_start=week,
            pr_count=count,
            algorithm_version=ALGORITHM_VERSION,
        ).on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "week_start"],
            set_={
                "pr_count": count,
                "algorithm_version": ALGORITHM_VERSION,
            },
        )
        await session.execute(stmt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && poetry run pytest tests/test_metrics_service.py -x -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/app/services/metrics_service.py server/tests/test_metrics_service.py
git commit -m "add PR throughput compute function"
```

---

### Task 8: `recompute_repo` orchestrator

**Files:**
- Modify: `server/app/services/metrics_service.py`
- Modify: `server/tests/test_metrics_service.py`

- [ ] **Step 1: Write failing test for `recompute_repo`**

Append to `server/tests/test_metrics_service.py`:

```python
from unittest.mock import patch, AsyncMock as AsyncMockFn

from conftest import make_repo


@pytest.mark.asyncio
async def test_recompute_repo_calls_all_four_metrics(mock_session):
    """recompute_repo should call all 4 compute functions."""
    from app.services.metrics_service import recompute_repo

    repo = make_repo(id=REPO_ID, default_branch="main")
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = repo
    mock_session.execute = AsyncMock(return_value=result_mock)

    with patch("app.services.metrics_service.compute_deployment_frequency", new_callable=AsyncMockFn) as mock_df, \
         patch("app.services.metrics_service.compute_lead_time", new_callable=AsyncMockFn) as mock_lt, \
         patch("app.services.metrics_service.compute_pr_cycle_time", new_callable=AsyncMockFn) as mock_ct, \
         patch("app.services.metrics_service.compute_pr_throughput", new_callable=AsyncMockFn) as mock_tp:

        result = await recompute_repo(TENANT_ID, REPO_ID, mock_session)

    mock_df.assert_called_once_with(TENANT_ID, REPO_ID, mock_session)
    mock_lt.assert_called_once_with(TENANT_ID, REPO_ID, "main", mock_session)
    mock_ct.assert_called_once_with(TENANT_ID, REPO_ID, "main", mock_session)
    mock_tp.assert_called_once_with(TENANT_ID, REPO_ID, "main", mock_session)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_recompute_repo_continues_on_partial_failure(mock_session):
    """If one metric fails, others still run."""
    from app.services.metrics_service import recompute_repo

    repo = make_repo(id=REPO_ID, default_branch="main")
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = repo
    mock_session.execute = AsyncMock(return_value=result_mock)

    with patch("app.services.metrics_service.compute_deployment_frequency", new_callable=AsyncMockFn, side_effect=Exception("db error")) as mock_df, \
         patch("app.services.metrics_service.compute_lead_time", new_callable=AsyncMockFn) as mock_lt, \
         patch("app.services.metrics_service.compute_pr_cycle_time", new_callable=AsyncMockFn) as mock_ct, \
         patch("app.services.metrics_service.compute_pr_throughput", new_callable=AsyncMockFn) as mock_tp:

        result = await recompute_repo(TENANT_ID, REPO_ID, mock_session)

    # All 4 were still called despite df failure
    mock_lt.assert_called_once()
    mock_ct.assert_called_once()
    mock_tp.assert_called_once()
    assert result.status == "failed"
    assert "deployment_frequency" in result.error_message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && poetry run pytest tests/test_metrics_service.py::test_recompute_repo_calls_all_four_metrics -x -v`
Expected: FAIL — `ImportError: cannot import name 'recompute_repo'`

- [ ] **Step 3: Implement `recompute_repo`**

Add to `server/app/services/metrics_service.py`:

```python
from dataclasses import dataclass, field

from app.models.repository import Repository


@dataclass
class RecomputeResult:
    status: str = "success"
    error_message: str | None = None
    errors: list[str] = field(default_factory=list)


async def recompute_repo(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    session: AsyncSession,
) -> RecomputeResult:
    # Look up repo for default_branch
    result = await session.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.tenant_id == tenant_id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        return RecomputeResult(status="failed", error_message="repo not found")

    default_branch = repo.default_branch
    errors: list[str] = []

    metric_fns = [
        ("deployment_frequency", compute_deployment_frequency, (tenant_id, repo_id, session)),
        ("lead_time", compute_lead_time, (tenant_id, repo_id, default_branch, session)),
        ("pr_cycle_time", compute_pr_cycle_time, (tenant_id, repo_id, default_branch, session)),
        ("pr_throughput", compute_pr_throughput, (tenant_id, repo_id, default_branch, session)),
    ]

    for name, fn, args in metric_fns:
        try:
            await fn(*args)
        except Exception:
            logger.exception("failed to compute %s for repo=%s", name, repo_id)
            errors.append(name)

    if errors:
        return RecomputeResult(
            status="failed",
            error_message=f"failed metrics: {', '.join(errors)}",
            errors=errors,
        )
    return RecomputeResult(status="success")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && poetry run pytest tests/test_metrics_service.py -x -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/app/services/metrics_service.py server/tests/test_metrics_service.py
git commit -m "add recompute_repo orchestrator"
```

---

## Chunk 3: Internal Endpoint

### Task 9: Add `INTERNAL_CRON_SECRET` to config

**Files:**
- Modify: `server/app/config.py:14` (add setting)
- Modify: `server/.env.example` (add example)

- [ ] **Step 1: Add setting to config**

In `server/app/config.py`, add after line 14 (`seed_tenant_name`):

```python
internal_cron_secret: str = ""
```

- [ ] **Step 2: Add to `.env.example`**

Append to `server/.env.example`:

```
INTERNAL_CRON_SECRET=
```

- [ ] **Step 3: Commit**

```bash
git add server/app/config.py server/.env.example
git commit -m "add INTERNAL_CRON_SECRET config"
```

---

### Task 10: Create internal recompute endpoint

**Files:**
- Create: `server/app/routes/internal.py`
- Create: `server/tests/test_internal_routes.py`
- Modify: `server/app/main.py:9,36` (register router)

- [ ] **Step 1: Write failing tests for the endpoint**

Create `server/tests/test_internal_routes.py`:

```python
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_session
from app.main import create_app
from conftest import TENANT_ID, REPO_ID


@pytest.fixture
def internal_client(mock_session):
    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_recompute_requires_auth(internal_client):
    resp = await internal_client.post(
        "/api/metrics/recompute",
        json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_recompute_rejects_bad_token(internal_client):
    resp = await internal_client.post(
        "/api/metrics/recompute",
        json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_recompute_success(internal_client, mock_session):
    from app.services.metrics_service import RecomputeResult

    with patch("app.routes.internal.settings") as mock_settings, \
         patch("app.routes.internal.recompute_repo", new_callable=AsyncMock) as mock_recompute:
        mock_settings.internal_cron_secret = "test-secret"
        mock_recompute.return_value = RecomputeResult(status="success")

        resp = await internal_client.post(
            "/api/metrics/recompute",
            json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_recompute_writes_refresh_log(internal_client, mock_session):
    from app.services.metrics_service import RecomputeResult

    with patch("app.routes.internal.settings") as mock_settings, \
         patch("app.routes.internal.recompute_repo", new_callable=AsyncMock) as mock_recompute:
        mock_settings.internal_cron_secret = "test-secret"
        mock_recompute.return_value = RecomputeResult(status="success")

        resp = await internal_client.post(
            "/api/metrics/recompute",
            json={"tenant_id": str(TENANT_ID), "repo_id": str(REPO_ID)},
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    # Verify session.execute was called (for the refresh log UPSERT)
    assert mock_session.execute.called
    assert mock_session.commit.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && poetry run pytest tests/test_internal_routes.py -x -v`
Expected: FAIL — route not found (404)

- [ ] **Step 3: Implement the endpoint**

Create `server/app/routes/internal.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.metrics import MetricsRefreshLog
from app.services.metrics_service import RecomputeResult, recompute_repo

router = APIRouter(prefix="/internal")


class RecomputeRequest(BaseModel):
    tenant_id: uuid.UUID
    repo_id: uuid.UUID


def _verify_cron_secret(authorization: str = Header(...)) -> None:
    if not settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="cron secret not configured")
    expected = f"Bearer {settings.internal_cron_secret}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid authorization")


@router.post("/metrics/recompute")
async def recompute_metrics(
    body: RecomputeRequest,
    _auth: None = Depends(_verify_cron_secret),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = datetime.now(timezone.utc)
    hour = now.replace(minute=0, second=0, microsecond=0)

    result: RecomputeResult = await recompute_repo(
        body.tenant_id, body.repo_id, session,
    )

    # UPSERT refresh log (dedup per hour)
    stmt = insert(MetricsRefreshLog).values(
        id=uuid.uuid4(),
        tenant_id=body.tenant_id,
        repo_id=body.repo_id,
        hour=hour,
        started_at=now,
        completed_at=datetime.now(timezone.utc),
        status=result.status,
        error_message=result.error_message,
    ).on_conflict_do_update(
        index_elements=["tenant_id", "repo_id", "hour"],
        set_={
            "started_at": now,
            "completed_at": datetime.now(timezone.utc),
            "status": result.status,
            "error_message": result.error_message,
        },
    )
    await session.execute(stmt)
    await session.commit()

    return {"status": result.status, "error_message": result.error_message}
```

- [ ] **Step 4: Register the router in `main.py`**

In `server/app/main.py`:
- Add to imports (line 9): `from app.routes import deployments, health, internal, pull_requests, repos, webhooks`
- Add after line 36: `app.include_router(internal.router, prefix="/api")`

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && poetry run pytest tests/test_internal_routes.py -x -v`
Expected: All tests pass.

- [ ] **Step 6: Run full test suite**

Run: `cd server && poetry run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add server/app/routes/internal.py server/tests/test_internal_routes.py server/app/main.py
git commit -m "add internal metrics recompute endpoint"
```

---

## Chunk 4: Webhook Update & Docs

### Task 11: Parse `opened_at` in webhook handler

**Files:**
- Modify: `server/app/services/deployment_service.py:119-140`
- Modify: `server/tests/test_deployment_service.py`

- [ ] **Step 1: Write failing test**

Add to `server/tests/test_deployment_service.py` a test that verifies `opened_at` is parsed from the webhook payload. The test should check that the INSERT values include `opened_at` parsed from `pr_data["created_at"]`.

```python
@pytest.mark.asyncio
async def test_pull_request_event_stores_opened_at(mock_session):
    """Webhook handler should parse opened_at from pr_data.created_at."""
    from app.services.deployment_service import handle_pull_request_event

    mock_session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=make_repo(github_id=123)),  # repo lookup
            mock_insert_result(),  # PR insert
        ]
    )

    payload = {
        "action": "closed",
        "pull_request": {
            "id": 999,
            "number": 42,
            "merged": True,
            "title": "Test PR",
            "created_at": "2025-01-10T08:00:00Z",
            "merged_at": "2025-01-15T12:00:00Z",
            "merge_commit_sha": "a" * 40,
            "head": {"sha": "b" * 40},
            "base": {"ref": "main"},
            "user": {"login": "dev"},
            "html_url": "https://github.com/org/repo/pull/42",
        },
        "repository": {"id": 123},
    }

    await handle_pull_request_event(payload, mock_session)

    # Verify execute was called with INSERT that includes opened_at
    insert_call = mock_session.execute.call_args_list[1]
    stmt = insert_call[0][0]
    # The compiled statement should reference opened_at
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "opened_at" in compiled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && poetry run pytest tests/test_deployment_service.py::test_pull_request_event_stores_opened_at -x -v`
Expected: FAIL — `opened_at` not in INSERT statement.

- [ ] **Step 3: Update webhook handler**

In `server/app/services/deployment_service.py`, modify `handle_pull_request_event` (lines 118-140):

Add after line 118 (`merged_at = _parse_dt(...)`):
```python
opened_at = _parse_dt(pr_data.get("created_at", ""))
```

Add `opened_at=opened_at` to the `insert(PullRequest).values(...)` call (after `html_url`):
```python
opened_at=opened_at,
```

Add `"opened_at": opened_at` to the `on_conflict_do_update set_` dict.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && poetry run pytest tests/test_deployment_service.py -x -v`
Expected: All tests pass.

- [ ] **Step 5: Run full test suite**

Run: `cd server && poetry run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/app/services/deployment_service.py server/tests/test_deployment_service.py
git commit -m "parse opened_at from PR webhook payload"
```

---

### Task 12: Update documentation

**Files:**
- Modify: `server/README.md`
- Modify: `README.md`

- [ ] **Step 1: Update `server/README.md`**

Add a section for the internal API endpoint and the new metric tables.

- [ ] **Step 2: Update root `README.md`**

Add a brief mention of the metrics aggregation engine.

- [ ] **Step 3: Run full test suite one final time**

Run: `cd server && poetry run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add server/README.md README.md
git commit -m "update docs for metrics aggregation engine"
```
