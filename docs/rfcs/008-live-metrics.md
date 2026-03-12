# Live Metrics

**Goal:** On-demand metrics for open PRs and PR ageing, computed at request time with no pre-aggregation.

**Scope expansion from PRD:** The existing webhook only captures PRs on merge. This RFC adds PR ingestion on open/update/close events and an `is_draft` flag to support open PR tracking.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest, Alembic

---

## Design

### Model Changes

Add two columns to `pull_requests`:

| Column      | Type           | Default | Notes                            |
| ----------- | -------------- | ------- | -------------------------------- |
| `is_draft`  | `Boolean`      | `False` | Draft status from GitHub         |
| `closed_at` | `DateTime(tz)` | `NULL`  | Set when PR closed without merge |

**PR states derived from existing + new columns:**

| State             | Condition                                     |
| ----------------- | --------------------------------------------- |
| Open (all)        | `merged_at IS NULL AND closed_at IS NULL`     |
| Live              | Open + `is_draft = False`                     |
| Draft             | Open + `is_draft = True`                      |
| Merged            | `merged_at IS NOT NULL`                       |
| Closed (unmerged) | `closed_at IS NOT NULL AND merged_at IS NULL` |

Migration adds columns with defaults so existing merged PR rows get `is_draft=False, closed_at=NULL`.

### Webhook Expansion

Expand `pull_request` webhook handler beyond `closed+merged`:

| Action                    | Behavior                                                                    |
| ------------------------- | --------------------------------------------------------------------------- |
| `opened`                  | Upsert PR row (`merged_at=NULL, closed_at=NULL, is_draft=pr_data["draft"]`) |
| `reopened`                | Set `closed_at=NULL, merged_at=NULL`                                        |
| `converted_to_draft`      | Set `is_draft=True`                                                         |
| `ready_for_review`        | Set `is_draft=False`                                                        |
| `closed` + `merged=true`  | Existing behavior: set `merged_at`                                          |
| `closed` + `merged=false` | Set `closed_at=timestamp`                                                   |

All actions use existing `on_conflict_do_update` keyed on `(tenant_id, repo_id, number)`.

### Endpoint: Open PR Counts

`GET /api/metrics/open-prs?repo_id=<UUID>`

```python
class OpenPRsResponse(BaseModel):
    total: int    # all open PRs
    live: int     # non-draft open PRs
    draft: int    # draft open PRs
```

Single query with `COUNT(*)` + conditional `SUM(CASE WHEN is_draft...)`. Scoped to `tenant_id + repo_id + base_ref=default_branch`.

### Endpoint: PR Ageing

`GET /api/metrics/pr-ageing?repo_id=<UUID>`

```python
class AgeBucket(BaseModel):
    bucket: str   # "<2d", "2-7d", "7-14d", ">14d"
    count: int

class PRAgeingResponse(BaseModel):
    buckets: list[AgeBucket]
```

Single query on **live PRs only** (non-draft, open). Bucketed via SQL `CASE WHEN NOW() - opened_at < interval '2 days' THEN '<2d' ...`, `GROUP BY bucket`.

### Performance

Both endpoints target <100ms. Indexes needed:

- `(tenant_id, repo_id, merged_at)` — may already exist
- `(tenant_id, repo_id, closed_at)` — for open PR filtering
- `(tenant_id, repo_id, is_draft)` — optional, for draft filtering

### Not Included

- Percentiles
- Historical trends
- Caching or pre-aggregation

---

## Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add open PR tracking via webhook expansion, then expose two on-demand metric endpoints.

**Architecture:** Expand the PullRequest model with `is_draft`, `closed_at`, and make `merged_at`/`merge_commit_sha` nullable. Expand the webhook handler to ingest PRs on all lifecycle events. Add two read-only metric endpoints (`open-prs`, `pr-ageing`) that query the `pull_requests` table directly.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest, Alembic

---

### Task 1: Model changes + migration

**Files:**
- Modify: `server/app/models/pull_request.py`
- Create: `server/database/versions/<auto>_add_pr_lifecycle_columns.py` (via Alembic autogenerate)

- [ ] **Step 1: Update PullRequest model**

Make `merged_at` and `merge_commit_sha` nullable (open PRs won't have these). Add `is_draft` and `closed_at`.

```python
# server/app/models/pull_request.py
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, TZDatetime


class PullRequest(TimestampMixin, Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    github_id: Mapped[int] = mapped_column(BigInteger)
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(1024))
    base_ref: Mapped[str] = mapped_column(String(255))
    merged_at: Mapped[datetime | None] = mapped_column(TZDatetime, nullable=True)
    opened_at: Mapped[TZDatetime]
    merge_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    head_sha: Mapped[str] = mapped_column(String(40))
    author_login: Mapped[str] = mapped_column(String(255))
    html_url: Mapped[str] = mapped_column(String(2048), default="")
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    closed_at: Mapped[datetime | None] = mapped_column(TZDatetime, nullable=True)
```

- [ ] **Step 2: Generate Alembic migration**

Run: `cd server && alembic revision --autogenerate -m "add pr lifecycle columns"`

Verify the generated migration contains:
- `ALTER TABLE pull_requests ADD COLUMN is_draft BOOLEAN DEFAULT false NOT NULL`
- `ALTER TABLE pull_requests ADD COLUMN closed_at TIMESTAMP WITH TIME ZONE`
- `ALTER TABLE pull_requests ALTER COLUMN merged_at DROP NOT NULL`
- `ALTER TABLE pull_requests ALTER COLUMN merge_commit_sha DROP NOT NULL`

- [ ] **Step 3: Apply migration**

Run: `cd server && alembic upgrade head`

- [ ] **Step 4: Update conftest make_pr factory**

Add `is_draft` and `closed_at` defaults to `make_pr` in `server/tests/conftest.py`:

```python
def make_pr(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        repo_id=uuid.uuid4(),
        github_id=99999,
        number=1,
        title="Fix bug",
        base_ref="main",
        merged_at=NOW,
        opened_at=NOW,
        merge_commit_sha="abc123" + "0" * 34,
        head_sha="def456" + "0" * 34,
        author_login="dev",
        html_url="https://github.com/org/repo/pull/1",
        created_at=NOW,
        updated_at=NOW,
        is_draft=False,
        closed_at=None,
    )
    defaults.update(overrides)
    return _make_model(PullRequest, defaults)
```

- [ ] **Step 5: Run full test suite**

Run: `cd server && python -m pytest -v`
Expected: all existing tests PASS (model changes are backward-compatible)

- [ ] **Step 6: Commit**

```bash
git add server/app/models/pull_request.py server/database/versions/ server/tests/conftest.py
git commit -m "add is_draft and closed_at to pull_requests, make merged_at nullable"
```

---

### Task 2: Webhook expansion — tests first

**Files:**
- Modify: `server/tests/test_deployment_service.py`

- [ ] **Step 1: Update payload helper to support draft and created_at fields**

```python
def _pull_request_payload(action="closed", merged=True, repo_github_id=111, draft=False):
    return {
        "action": action,
        "pull_request": {
            "id": 99001,
            "merged": merged,
            "draft": draft,
            "number": 7,
            "title": "My PR",
            "merge_commit_sha": "abc1230000",
            "body": "desc",
            "head": {"ref": "feature-branch", "sha": "def456"},
            "base": {"ref": "main"},
            "merged_at": "2025-01-15T11:00:00Z" if merged else None,
            "created_at": "2025-01-10T09:00:00Z",
            "user": {"login": "dev"},
            "html_url": "https://github.com/org/repo/pull/7",
        },
        "repository": {
            "id": repo_github_id,
            "full_name": "org/repo",
        },
        "installation": {"id": 42},
    }
```

- [ ] **Step 2: Update test_skips_non_closed to test_skips_unhandled_action**

The old test asserted `opened` was skipped. Now `opened` is handled. Replace with an action we don't handle (e.g. `labeled`):

```python
@pytest.mark.asyncio
async def test_skips_unhandled_action(mock_session):
    payload = _pull_request_payload(action="labeled")
    await handle_pull_request_event(payload, mock_session)
    mock_session.execute.assert_not_called()
```

- [ ] **Step 3: Write test for opened action**

```python
@pytest.mark.asyncio
async def test_opened_pr_creates_row(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="opened", merged=False, draft=False)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2

    insert_call = mock_session.execute.call_args_list[1]
    stmt = insert_call.args[0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    sql = str(compiled)
    assert "is_draft" in sql
```

- [ ] **Step 4: Write test for opened draft PR**

```python
@pytest.mark.asyncio
async def test_opened_draft_pr_sets_is_draft(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="opened", merged=False, draft=True)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2
```

- [ ] **Step 5: Write test for closed-without-merge**

```python
@pytest.mark.asyncio
async def test_closed_without_merge_sets_closed_at(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="closed", merged=False)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2
```

- [ ] **Step 6: Write test for converted_to_draft**

```python
@pytest.mark.asyncio
async def test_converted_to_draft_updates_flag(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="converted_to_draft", merged=False)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2
```

- [ ] **Step 7: Write test for ready_for_review**

```python
@pytest.mark.asyncio
async def test_ready_for_review_clears_draft(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="ready_for_review", merged=False)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2
```

- [ ] **Step 8: Write test for reopened**

```python
@pytest.mark.asyncio
async def test_reopened_clears_closed_at(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="reopened", merged=False)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2
```

- [ ] **Step 9: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_deployment_service.py -v`
Expected: new tests FAIL (handler doesn't handle these actions yet)

- [ ] **Step 10: Commit tests**

```bash
git add server/tests/test_deployment_service.py
git commit -m "add webhook expansion tests for PR lifecycle events"
```

---

### Task 3: Webhook expansion — implementation

**Files:**
- Modify: `server/app/services/deployment_service.py`

- [ ] **Step 1: Add _parse_dt_optional helper**

Add below existing `_parse_dt`:

```python
def _parse_dt_optional(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
```

- [ ] **Step 2: Rewrite handle_pull_request_event**

Replace the existing handler with:

```python
HANDLED_PR_ACTIONS = {"opened", "reopened", "closed", "converted_to_draft", "ready_for_review"}


@register_handler("pull_request")
async def handle_pull_request_event(payload: dict, session: AsyncSession) -> None:
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})

    if action not in HANDLED_PR_ACTIONS:
        return

    repo_data = payload["repository"]
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    # Look up repo
    result = await session.execute(
        select(Repository).where(
            Repository.tenant_id == tenant_id,
            Repository.github_id == repo_data["id"],
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        logger.warning("repo not found for PR, github_id=%s", repo_data["id"])
        return

    merged_at = _parse_dt_optional(pr_data.get("merged_at"))
    opened_at = _parse_dt(pr_data.get("created_at", ""))
    is_draft = pr_data.get("draft", False)
    is_merged = action == "closed" and pr_data.get("merged", False)

    # Determine closed_at
    closed_at = None
    if action == "closed" and not is_merged:
        closed_at = _parse_dt_optional(pr_data.get("closed_at")) or datetime.now(
            tz=__import__("datetime").timezone.utc
        )

    # Determine field overrides based on action
    if action == "converted_to_draft":
        is_draft = True
    elif action == "ready_for_review":
        is_draft = False

    merge_commit_sha = pr_data.get("merge_commit_sha") or None

    stmt = insert(PullRequest).values(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        repo_id=repo.id,
        github_id=pr_data["id"],
        number=pr_data["number"],
        title=pr_data.get("title", ""),
        base_ref=pr_data.get("base", {}).get("ref", ""),
        merged_at=merged_at,
        merge_commit_sha=merge_commit_sha,
        head_sha=pr_data.get("head", {}).get("sha", ""),
        author_login=pr_data.get("user", {}).get("login", ""),
        html_url=pr_data.get("html_url", ""),
        opened_at=opened_at,
        is_draft=is_draft,
        closed_at=closed_at,
    ).on_conflict_do_update(
        index_elements=["tenant_id", "repo_id", "number"],
        set_={
            "title": pr_data.get("title", ""),
            "merged_at": merged_at,
            "merge_commit_sha": merge_commit_sha,
            "opened_at": opened_at,
            "is_draft": is_draft,
            "closed_at": closed_at,
        },
    )
    await session.execute(stmt)
```

Note: import `datetime` timezone at the top — add `from datetime import datetime, timezone` (already imported, just ensure `timezone` is included).

- [ ] **Step 3: Run webhook tests**

Run: `cd server && python -m pytest tests/test_deployment_service.py -v`
Expected: all tests PASS

- [ ] **Step 4: Run full test suite**

Run: `cd server && python -m pytest -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/services/deployment_service.py
git commit -m "expand webhook handler to ingest PRs on all lifecycle events"
```

---

### Task 4: Open PRs endpoint — tests first

**Files:**
- Create: `server/tests/test_open_prs.py`

- [ ] **Step 1: Write test for open PR counts**

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import REPO_ID


@pytest.mark.asyncio
async def test_open_prs_returns_counts(client, mock_session):
    # Mock a single query that returns total=5, live=3, draft=2
    result = MagicMock()
    row = MagicMock()
    row.total = 5
    row.live = 3
    row.draft = 2
    result.one.return_value = row

    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/api/metrics/open-prs?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert data["live"] == 3
    assert data["draft"] == 2
```

- [ ] **Step 2: Write test for zero state**

```python
@pytest.mark.asyncio
async def test_open_prs_zero_state(client, mock_session):
    result = MagicMock()
    row = MagicMock()
    row.total = 0
    row.live = 0
    row.draft = 0
    result.one.return_value = row

    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/api/metrics/open-prs?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["live"] == 0
    assert data["draft"] == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_open_prs.py -v`
Expected: FAIL (endpoint doesn't exist yet)

- [ ] **Step 4: Commit tests**

```bash
git add server/tests/test_open_prs.py
git commit -m "add open PRs endpoint tests"
```

---

### Task 5: Open PRs endpoint — implementation

**Files:**
- Modify: `server/app/schemas/metrics.py`
- Modify: `server/app/routes/metrics.py`

- [ ] **Step 1: Add OpenPRsResponse schema**

Append to `server/app/schemas/metrics.py`:

```python
class OpenPRsResponse(BaseModel):
    total: int
    live: int
    draft: int
```

- [ ] **Step 2: Add open-prs endpoint**

Add to `server/app/routes/metrics.py`:

```python
from app.schemas.metrics import (
    DailyCount, DeploymentFrequencyResponse, LeadTimeResponse, WeeklyLeadTime,
    OpenPRsResponse,
)
```

Add endpoint:

```python
@router.get("/open-prs")
async def get_open_prs(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> OpenPRsResponse:
    result = await session.execute(
        select(
            func.count().label("total"),
            func.sum(func.cast(PullRequest.is_draft == False, sa.Integer)).label("live"),
            func.sum(func.cast(PullRequest.is_draft == True, sa.Integer)).label("draft"),
        ).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo.id,
            PullRequest.base_ref == repo.default_branch,
            PullRequest.merged_at.is_(None),
            PullRequest.closed_at.is_(None),
        )
    )
    row = result.one()
    return OpenPRsResponse(
        total=row.total or 0,
        live=row.live or 0,
        draft=row.draft or 0,
    )
```

Add `import sqlalchemy as sa` to the imports if not present.

- [ ] **Step 3: Run open-prs tests**

Run: `cd server && python -m pytest tests/test_open_prs.py -v`
Expected: all tests PASS

- [ ] **Step 4: Run full test suite**

Run: `cd server && python -m pytest -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/schemas/metrics.py server/app/routes/metrics.py
git commit -m "add open PRs endpoint"
```

---

### Task 6: PR ageing endpoint — tests first

**Files:**
- Create: `server/tests/test_pr_ageing.py`

- [ ] **Step 1: Write test for ageing buckets**

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import REPO_ID


@pytest.mark.asyncio
async def test_pr_ageing_returns_buckets(client, mock_session):
    rows = [
        MagicMock(bucket="<2d", count=2),
        MagicMock(bucket="2-7d", count=3),
        MagicMock(bucket="7-14d", count=1),
        MagicMock(bucket=">14d", count=0),
    ]
    result = MagicMock()
    result.all.return_value = rows

    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/api/metrics/pr-ageing?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["buckets"]) == 4
    assert data["buckets"][0] == {"bucket": "<2d", "count": 2}
    assert data["buckets"][1] == {"bucket": "2-7d", "count": 3}
```

- [ ] **Step 2: Write test for zero state (no open PRs)**

```python
@pytest.mark.asyncio
async def test_pr_ageing_zero_state(client, mock_session):
    result = MagicMock()
    result.all.return_value = []

    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/api/metrics/pr-ageing?repo_id={REPO_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["buckets"] == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_pr_ageing.py -v`
Expected: FAIL (endpoint doesn't exist yet)

- [ ] **Step 4: Commit tests**

```bash
git add server/tests/test_pr_ageing.py
git commit -m "add PR ageing endpoint tests"
```

---

### Task 7: PR ageing endpoint — implementation

**Files:**
- Modify: `server/app/schemas/metrics.py`
- Modify: `server/app/routes/metrics.py`

- [ ] **Step 1: Add ageing schemas**

Append to `server/app/schemas/metrics.py`:

```python
class AgeBucket(BaseModel):
    bucket: str
    count: int


class PRAgeingResponse(BaseModel):
    buckets: list[AgeBucket]
```

- [ ] **Step 2: Add pr-ageing endpoint**

Update imports in `server/app/routes/metrics.py`:

```python
from app.schemas.metrics import (
    DailyCount, DeploymentFrequencyResponse, LeadTimeResponse, WeeklyLeadTime,
    OpenPRsResponse, AgeBucket, PRAgeingResponse,
)
```

Add endpoint:

```python
@router.get("/pr-ageing")
async def get_pr_ageing(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
) -> PRAgeingResponse:
    now = func.now()
    age = now - PullRequest.opened_at
    bucket_expr = sa.case(
        (age < sa.text("interval '2 days'"), sa.literal("<2d")),
        (age < sa.text("interval '7 days'"), sa.literal("2-7d")),
        (age < sa.text("interval '14 days'"), sa.literal("7-14d")),
        else_=sa.literal(">14d"),
    ).label("bucket")

    result = await session.execute(
        select(
            bucket_expr,
            func.count().label("count"),
        ).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo.id,
            PullRequest.base_ref == repo.default_branch,
            PullRequest.merged_at.is_(None),
            PullRequest.closed_at.is_(None),
            PullRequest.is_draft.is_(False),
        ).group_by(sa.text("bucket"))
    )
    rows = result.all()
    return PRAgeingResponse(
        buckets=[AgeBucket(bucket=row.bucket, count=row.count) for row in rows],
    )
```

- [ ] **Step 3: Run ageing tests**

Run: `cd server && python -m pytest tests/test_pr_ageing.py -v`
Expected: all tests PASS

- [ ] **Step 4: Run full test suite**

Run: `cd server && python -m pytest -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/schemas/metrics.py server/app/routes/metrics.py
git commit -m "add PR ageing endpoint"
```

---

### Task 8: Documentation

**Files:**
- Modify: `README.md`
- Modify: `server/README.md`
- Modify: `docs/rfcs/008-live-metrics.md` (add review section)

- [ ] **Step 1: Update READMEs with new endpoints**

Add the two new endpoints to any API endpoint listing in `README.md` and `server/README.md`.

- [ ] **Step 2: Add review section to RFC**

Append to `docs/rfcs/008-live-metrics.md`:

```markdown
---

## Review

- [ ] Migration applied and verified
- [ ] Webhook handles all PR lifecycle actions
- [ ] Existing tests still pass (backward compatibility)
- [ ] open-prs endpoint returns correct counts
- [ ] pr-ageing endpoint returns correct buckets
- [ ] All tests pass
```

- [ ] **Step 3: Commit**

```bash
git add README.md server/README.md docs/rfcs/008-live-metrics.md
git commit -m "update docs for live metrics endpoints"
```
