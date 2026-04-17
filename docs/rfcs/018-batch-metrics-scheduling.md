# RFC 018: Batch Metrics Scheduling

**Goal:** Reliably trigger hourly metric recomputes for every tenant + repo via a Railway scheduled job that fans out to the existing per-repo endpoint.

**Architecture:** A Railway cron service runs a small Python script hourly. The script authenticates with `INTERNAL_CRON_SECRET`, asks the server for the current list of `(tenant_id, repo_id)` pairs, then POSTs to `/metrics/recompute` once per repo with small stagger and bounded concurrency. The existing endpoint already provides isolation, idempotency, and per-hour dedup via `metrics_refresh_log`.

**Tech Stack:** FastAPI, SQLAlchemy async, Railway cron service, Python `httpx`, existing `pytest` suite.

---

## Background

- `POST /metrics/recompute` (`server/app/routes/metrics.py:61`) already computes all four metrics for a single `(tenant_id, repo_id)` and writes a refresh log entry (deduped on `(tenant_id, repo_id, hour)`).
- Nothing currently calls the endpoint on a schedule — recomputation only happens ad hoc.
- PRD 012 (`docs/prds/012 - Scheduled Infrastructure.md`) specified a Railway scheduled job with staggered per-repo HTTP fan-out; this RFC is the technical design for it.
- RFC 005 (`docs/rfcs/005-metrics-aggregation-engine.md:15-18`) deliberately chose per-repo recompute over a single bulk endpoint to isolate blast radius and allow staggering — this design preserves that invariant.

## Design Decisions

### Keep the per-repo endpoint as the unit of work

The scheduler does not introduce a new bulk recompute code path. One repo = one HTTP call = one DB transaction = one refresh log row. If a repo fails, the rest continue. This is the property PRD 012 and RFC 005 were designed around; we do not want to regress it by adding an in-process loop behind a single long-running endpoint.

### Fan-out in a Railway cron script, not in the app process

The scheduler lives as a standalone script (`server/scripts/run_hourly_recompute.py`) invoked by Railway on a cron schedule. It is **not** a FastAPI background task or in-process scheduler. This keeps the web process stateless and horizontally scalable, avoids "who owns the schedule?" problems if multiple instances run, and makes job observability (exit code, logs, Railway run history) first-class.

### Server exposes an enumeration endpoint, scheduler consumes it

The scheduler needs the list of `(tenant_id, repo_id)` pairs. Rather than giving the scheduler direct DB credentials, we add a new authenticated endpoint:

- `GET /metrics/recompute-targets` → `{ "targets": [{ "tenant_id": "...", "repo_id": "..." }, ...] }`
- Authenticated with the existing `INTERNAL_CRON_SECRET` bearer token (same scheme as `/recompute`).
- Rate-limited and scoped to the cron-secret privilege boundary.

This keeps DB access inside the server (one connection pool, one SSL policy, one migration story) and avoids shipping database credentials into a second runtime.

### Staggered, bounded-concurrency fan-out

The scheduler processes repos with a small worker pool (default: 3 concurrent requests) and a per-request jitter of 0–2s. Reasons:

- **Bounded concurrency** protects the web process and DB from an N-wide thundering herd when we grow to many repos.
- **Jitter** smooths sub-second spikes when multiple workers return a response at the same moment.
- Serial-only fan-out would not finish hourly once we exceed ~1500 repos at 2s each; pure parallel would overload the DB. A small pool is the right middle.

### Per-call timeout + single retry

Each HTTP call has a 120s timeout. On connection error or 5xx, the scheduler retries **once** after a 5s delay, then logs the failure and moves on. The endpoint itself is idempotent per hour via the refresh-log UPSERT, so a retry cannot double-count. No queueing, no exponential backoff — PRD 012 explicitly defers those.

### Scheduler is defensive about partial failure

A single repo's failure never aborts the run. The script collects per-repo outcomes, writes a structured summary line at the end, and exits:

- `exit 0` — all repos succeeded (or the endpoint responded non-2xx but the per-repo refresh log captured the failure).
- `exit 1` — the scheduler itself could not enumerate targets or lost connectivity. This is the signal Railway alerts on.

Individual repo failures are visible in `metrics_refresh_log` (status / error_message columns), not in the script exit code. This matches the existing observability pattern.

### Idempotency, safe to re-run

Because the endpoint UPSERTs per-hour on `(tenant_id, repo_id, hour)`, re-running the scheduler within the same hour is safe and produces the same result. Operators can kick off a manual run without worrying about duplicate writes.

### Existing security posture is preserved, not widened

The new enumeration endpoint shares the `INTERNAL_CRON_SECRET` privilege boundary already in use by `/recompute`. RFC 017 finding H-5 notes this secret has tenant-spanning privileges — we are not changing that. No new secret, no new auth path, no new attack surface beyond the enumeration response itself (which returns only internal UUIDs, no tenant content). We rate-limit the new endpoint the same way.

## Scope

In scope:
- New enumeration endpoint `GET /metrics/recompute-targets`.
- New scheduler script `server/scripts/run_hourly_recompute.py`.
- Railway configuration (`railway.toml`) defining the cron service and its start command.
- `API_BASE_URL` config value so the script knows which deployment to target.
- Tests for the enumeration endpoint and the scheduler's fan-out loop (mocked HTTP).
- Documentation updates: `server/README.md`, `docs/prds/012 - Scheduled Infrastructure.md` cross-link, ADR if we capture the "fan-out lives outside the web process" decision.

Out of scope (explicitly deferred per PRD 012):
- Distributed job queue (Celery / Arq / RQ).
- Exponential backoff retries.
- Per-tenant scheduler authentication (still cron-secret).
- Caching or pre-aggregation beyond what RFC 005 built.
- Partial/incremental recompute (we always recompute the 90-day window per repo).

## Schema Changes

**None.** All required tables and columns exist (RFC 005). `metrics_refresh_log` is the source of truth for per-run outcomes.

## New API

### `GET /metrics/recompute-targets`

- **Auth:** `Authorization: Bearer <INTERNAL_CRON_SECRET>`, validated with `hmac.compare_digest` (same helper as `/recompute`). The existing `_verify_cron_secret` dependency in `server/app/routes/metrics.py:52` is reused.
- **Rate limit:** Reuses the `@limiter.limit("10/minute")` decorator pattern; the scheduler calls this once per run.
- **Response:**
  ```json
  {
    "targets": [
      {"tenant_id": "uuid", "repo_id": "uuid"}
    ],
    "count": 42
  }
  ```
- **Query:** `SELECT id AS repo_id, tenant_id FROM repositories` — no joins, no filters on tenant status yet. If we introduce tenant suspension later, add `WHERE tenants.status = 'active'`.
- **Ordering:** Deterministic (`ORDER BY tenant_id, repo_id`) so two consecutive runs produce the same fan-out order for reproducibility in logs.

## Scheduler Script

### Location

`server/scripts/run_hourly_recompute.py` — lives alongside `seed_demo.py` / `reset_demo.py`, run via `poetry run python scripts/run_hourly_recompute.py`.

### Config

Reads from env:

| Var                      | Purpose                                           |
| ------------------------ | ------------------------------------------------- |
| `API_BASE_URL`           | e.g. `https://distilled.up.railway.app`           |
| `INTERNAL_CRON_SECRET`   | Shared secret for the two internal endpoints      |
| `RECOMPUTE_CONCURRENCY`  | Worker count (default `3`)                        |
| `RECOMPUTE_JITTER_MS`    | Max jitter per call in ms (default `2000`)        |
| `RECOMPUTE_TIMEOUT_S`    | Per-call HTTP timeout in seconds (default `120`)  |

### Flow

```
1. Load config; fail fast if API_BASE_URL or INTERNAL_CRON_SECRET missing.
2. GET /api/metrics/recompute-targets  → list of {tenant_id, repo_id}
3. Fan out with asyncio.Semaphore(RECOMPUTE_CONCURRENCY):
     for each target:
       sleep(random.uniform(0, JITTER))
       POST /api/metrics/recompute  with {tenant_id, repo_id}
       on connection error / 5xx: wait 5s, retry once
       record outcome
4. Print structured summary: total / succeeded / failed / duration.
5. Exit 0 (normal completion) or 1 (scheduler-level failure: enumeration unreachable).
```

### Observability

- One structured log line per repo: `{"event": "recompute", "tenant_id": "...", "repo_id": "...", "status": "...", "duration_ms": ...}`.
- Final summary line: `{"event": "recompute_run_complete", "total": N, "succeeded": S, "failed": F, "duration_s": D}`.
- Per-repo failure state is **already** persisted in `metrics_refresh_log` via the endpoint — the scheduler does not duplicate that write.

## Railway Configuration

Create a **new Railway service** in the existing project, pointed at the same repo but with a cron schedule and its own start command. Railway runs a cron service by invoking `startCommand` on the schedule and expects the process to exit cleanly when the task completes — this matches our script's contract.

**Key Railway constraints (per Railway's cron docs):**

- Minimum interval between runs is 5 minutes — we use hourly, so fine.
- Schedules are evaluated in **UTC**.
- Services configured as cron jobs must exit cleanly (no lingering DB connections, no long-lived event loops).
- If a previous run is still executing when the next is due, Railway skips the new run — overlap is not an issue we need to handle in the script.

**Config file:** add `server/railway.toml` for the cron service (the web service keeps its dashboard-managed config):

```toml
[deploy]
startCommand = "poetry run python scripts/run_hourly_recompute.py"
cronSchedule = "0 * * * *"
restartPolicyType = "never"
```

- `cronSchedule = "0 * * * *"` runs at the top of every hour (UTC).
- `restartPolicyType = "never"` keeps Railway from looping the script on non-zero exit — a scheduler-level failure surfaces once, gets logged, and the next hourly tick retries naturally.

**Env vars (set on the cron service only):**

| Var                     | Value                                         |
| ----------------------- | --------------------------------------------- |
| `API_BASE_URL`          | Internal Railway URL of the web service       |
| `INTERNAL_CRON_SECRET`  | Same secret the web service validates against |
| `RECOMPUTE_CONCURRENCY` | Optional; defaults to `3`                     |

The cron service does **not** need `DATABASE_URL` — it only talks to the web API.

## Config Changes

- Add `app_base_url: str = ""` to `server/app/config.py` (only used by scripts, but belongs in one place).
- Validate at script entry that it is non-empty — the web app itself does not require it.
- Add to `server/.env.example`: `API_BASE_URL=`.

## Testing Strategy

- **Endpoint tests** (`tests/test_metrics_routes.py` — extend existing file):
  - `test_recompute_targets_requires_auth` → 401 without bearer.
  - `test_recompute_targets_rejects_bad_token` → 401 with wrong secret.
  - `test_recompute_targets_returns_all_repos` → creates 2 tenants × 2 repos, expects 4 targets.
  - `test_recompute_targets_ordering_is_stable` → two successive calls return identical order.
- **Scheduler tests** (`tests/test_run_hourly_recompute.py`):
  - Mock httpx transport to return canned target list + per-repo responses.
  - Verify: correct number of POSTs, bounded concurrency respected, one-retry behaviour on 5xx, exit 1 when enumeration fails, exit 0 with mixed per-repo failures.
- No integration test against a real Railway cron — verified manually in staging before production cutover.

## Rollout

No staging environment exists yet, and we have no real customers, so risk is low. The plan is:

1. Merge endpoint + script + `railway.toml` + tests. The script is dormant in production until the cron service is provisioned.
2. **Local smoke test:** run the web server locally against the demo seed, then run `poetry run python scripts/run_hourly_recompute.py` with `API_BASE_URL=http://localhost:8000` and a local cron secret. Verify `metrics_refresh_log` rows appear for every seeded repo and the dashboard reflects fresh numbers.
3. **Production smoke test:** invoke the script once manually against the production URL (e.g. via `railway run` or a local shell with prod env vars) **before** enabling the schedule. Confirm one full clean run.
4. Provision the Railway cron service from `server/railway.toml`. Let one hourly tick land and verify in the Railway run history and `metrics_refresh_log`.
5. Keep an eye on Railway's run history for the first 48h. If exit codes start failing, treat as a bug and fix forward.

## Resolved Questions

1. **Filter targets by recent activity?** No — keep the fan-out dumb. The compute functions no-op cheaply for empty data and the refresh log still captures the "we tried" record, which is useful signal.
2. **Prometheus metrics from the script?** No — Railway log aggregation is sufficient for now. PRD 012 explicitly defers distributed-queue-style observability.
3. **Persist run summaries to a dedicated `cron_run_log` table?** No — `max(completed_at)` over `metrics_refresh_log` gives us "last successful refresh per repo" without a new table.

---

# Implementation Plan

> **For agentic workers:** Use red/green TDD — write the failing test first, verify it fails, implement, verify it passes, commit. Steps use checkbox (`- [ ]`) syntax for tracking.

## Chunk 1: Enumeration Endpoint

### Task 1: Add `recompute-targets` endpoint tests

**Files:**
- Modify: `server/tests/test_metrics_routes.py` (append new tests)

- [ ] **Step 1: Add failing tests**

Append to `server/tests/test_metrics_routes.py` a new block of tests for `GET /metrics/recompute-targets`. Cover:

- Missing `Authorization` header → 403 (FastAPI `HTTPBearer` behaviour, matches `test_recompute_requires_auth`).
- Wrong bearer token → 401.
- Valid bearer + zero repos → `200` with `{"targets": [], "count": 0}`.
- Valid bearer + multiple repos across two tenants → `200` with a sorted list and correct `count`.

```python
@pytest.mark.asyncio
async def test_recompute_targets_requires_auth(metrics_client):
    resp = await metrics_client.get("/metrics/recompute-targets")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recompute_targets_rejects_bad_token(metrics_client):
    resp = await metrics_client.get(
        "/metrics/recompute-targets",
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_recompute_targets_returns_sorted_list(metrics_client, mock_session):
    tenant_a = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
    tenant_b = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
    repo_a1 = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
    repo_a2 = uuid.UUID("00000000-0000-0000-0000-0000000000a3")
    repo_b1 = uuid.UUID("00000000-0000-0000-0000-0000000000b2")

    rows = [(tenant_a, repo_a1), (tenant_a, repo_a2), (tenant_b, repo_b1)]
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=result_mock)

    with patch("app.routes.metrics.settings") as mock_settings:
        mock_settings.internal_cron_secret = "test-secret"
        resp = await metrics_client.get(
            "/metrics/recompute-targets",
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    assert body["targets"] == [
        {"tenant_id": str(tenant_a), "repo_id": str(repo_a1)},
        {"tenant_id": str(tenant_a), "repo_id": str(repo_a2)},
        {"tenant_id": str(tenant_b), "repo_id": str(repo_b1)},
    ]
```

Also add `import uuid` at the top of the file if not already present.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd server && poetry run pytest tests/test_metrics_routes.py -x -v -k recompute_targets
```

Expected: 404 / route not found on the three cases that reach the endpoint.

---

### Task 2: Implement `recompute-targets` endpoint

**Files:**
- Modify: `server/app/routes/metrics.py`

- [ ] **Step 1: Add the route handler**

In `server/app/routes/metrics.py`, add below `recompute_metrics`:

```python
@router.get("/recompute-targets")
@limiter.limit("10/minute")
async def list_recompute_targets(
    request: Request,
    _auth: None = Depends(_verify_cron_secret),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Repository.tenant_id, Repository.id)
        .order_by(Repository.tenant_id, Repository.id)
    )
    rows = result.all()
    targets = [
        {"tenant_id": str(tenant_id), "repo_id": str(repo_id)}
        for tenant_id, repo_id in rows
    ]
    return {"targets": targets, "count": len(targets)}
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd server && poetry run pytest tests/test_metrics_routes.py -x -v
```

Expected: all tests in the file pass (including the four new ones).

- [ ] **Step 3: Run the full server test suite**

```bash
cd server && poetry run pytest -x -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add server/app/routes/metrics.py server/tests/test_metrics_routes.py
git commit -m "feat: add recompute-targets enumeration endpoint"
```

---

## Chunk 2: Scheduler Script

### Task 3: Scaffold the script and write failing tests

**Files:**
- Create: `server/scripts/run_hourly_recompute.py`
- Create: `server/tests/test_run_hourly_recompute.py`

- [ ] **Step 1: Create a minimal script skeleton**

Create `server/scripts/run_hourly_recompute.py` with only the imports, a module docstring, and a `main()` that does nothing yet. This gives the tests something to import without failing on module load.

```python
"""Hourly batch metrics recompute.

Usage:
    cd server && API_BASE_URL=http://localhost:8000 \
        INTERNAL_CRON_SECRET=... \
        PYTHONPATH=. poetry run python scripts/run_hourly_recompute.py
"""

import asyncio
import os
import random
import sys
import time
from dataclasses import dataclass

import httpx


@dataclass
class RunSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duration_s: float = 0.0


async def fetch_targets(client: httpx.AsyncClient) -> list[dict]:
    raise NotImplementedError


async def recompute_one(client: httpx.AsyncClient, target: dict) -> bool:
    raise NotImplementedError


async def run() -> RunSummary:
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write failing tests**

Create `server/tests/test_run_hourly_recompute.py`:

```python
import asyncio
from unittest.mock import patch

import httpx
import pytest

from scripts import run_hourly_recompute as sut


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_fetch_targets_calls_enumeration_endpoint():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "targets": [
                    {"tenant_id": "t1", "repo_id": "r1"},
                    {"tenant_id": "t1", "repo_id": "r2"},
                ],
                "count": 2,
            },
        )

    async with httpx.AsyncClient(
        transport=_mock_transport(handler),
        base_url="http://test",
        headers={"Authorization": "Bearer s"},
    ) as client:
        targets = await sut.fetch_targets(client)

    assert len(targets) == 2
    assert calls[0].url.path == "/metrics/recompute-targets"
    assert calls[0].headers["Authorization"] == "Bearer s"


@pytest.mark.asyncio
async def test_recompute_one_returns_true_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/metrics/recompute"
        return httpx.Response(200, json={"status": "success", "error_message": None})

    async with httpx.AsyncClient(transport=_mock_transport(handler), base_url="http://test") as client:
        ok = await sut.recompute_one(client, {"tenant_id": "t1", "repo_id": "r1"})

    assert ok is True


@pytest.mark.asyncio
async def test_recompute_one_retries_once_on_5xx():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, json={"detail": "transient"})
        return httpx.Response(200, json={"status": "success"})

    async with httpx.AsyncClient(transport=_mock_transport(handler), base_url="http://test") as client:
        with patch.object(sut.asyncio, "sleep", new=lambda _s: asyncio.sleep(0)):
            ok = await sut.recompute_one(client, {"tenant_id": "t1", "repo_id": "r1"})

    assert ok is True
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_recompute_one_gives_up_after_one_retry():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=_mock_transport(handler), base_url="http://test") as client:
        with patch.object(sut.asyncio, "sleep", new=lambda _s: asyncio.sleep(0)):
            ok = await sut.recompute_one(client, {"tenant_id": "t1", "repo_id": "r1"})

    assert ok is False
    assert attempts["n"] == 2  # initial + one retry


@pytest.mark.asyncio
async def test_run_fans_out_for_every_target(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")
    monkeypatch.setenv("RECOMPUTE_JITTER_MS", "0")
    monkeypatch.setenv("RECOMPUTE_CONCURRENCY", "2")

    call_log: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        call_log.append(request.url.path)
        if request.url.path.endswith("recompute-targets"):
            return httpx.Response(200, json={
                "targets": [
                    {"tenant_id": "t1", "repo_id": "r1"},
                    {"tenant_id": "t1", "repo_id": "r2"},
                    {"tenant_id": "t1", "repo_id": "r3"},
                ],
                "count": 3,
            })
        return httpx.Response(200, json={"status": "success"})

    with patch.object(sut.httpx, "AsyncClient", lambda **kw: httpx.AsyncClient(transport=_mock_transport(handler), **kw)):
        summary = await sut.run()

    assert summary.total == 3
    assert summary.succeeded == 3
    assert summary.failed == 0
    # 1 enumeration + 3 recomputes
    assert call_log.count("/metrics/recompute") == 3


def test_main_exits_1_on_enumeration_failure(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with patch.object(sut.httpx, "AsyncClient", lambda **kw: httpx.AsyncClient(transport=_mock_transport(handler), **kw)):
        code = sut.main()

    assert code == 1


def test_main_exits_0_on_partial_per_repo_failure(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")
    monkeypatch.setenv("RECOMPUTE_JITTER_MS", "0")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("recompute-targets"):
            return httpx.Response(200, json={
                "targets": [{"tenant_id": "t1", "repo_id": "r1"}],
                "count": 1,
            })
        return httpx.Response(500)

    with patch.object(sut.httpx, "AsyncClient", lambda **kw: httpx.AsyncClient(transport=_mock_transport(handler), **kw)), \
         patch.object(sut.asyncio, "sleep", new=lambda _s: asyncio.sleep(0)):
        code = sut.main()

    # Per-repo failures are NOT a scheduler-level failure.
    assert code == 0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd server && poetry run pytest tests/test_run_hourly_recompute.py -x -v
```

Expected: every test raises `NotImplementedError`.

- [ ] **Step 4: Commit the scaffolding (red state)**

```bash
git add server/scripts/run_hourly_recompute.py server/tests/test_run_hourly_recompute.py
git commit -m "test: add failing tests for hourly recompute scheduler"
```

---

### Task 4: Implement the scheduler

**Files:**
- Modify: `server/scripts/run_hourly_recompute.py`

- [ ] **Step 1: Replace `NotImplementedError` bodies with the real logic**

```python
JITTER_MS = int(os.environ.get("RECOMPUTE_JITTER_MS", "2000"))
CONCURRENCY = int(os.environ.get("RECOMPUTE_CONCURRENCY", "3"))
TIMEOUT_S = float(os.environ.get("RECOMPUTE_TIMEOUT_S", "120"))
RETRY_DELAY_S = 5.0


async def fetch_targets(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get("/metrics/recompute-targets")
    resp.raise_for_status()
    return resp.json()["targets"]


async def recompute_one(client: httpx.AsyncClient, target: dict) -> bool:
    for attempt in range(2):  # initial + one retry
        try:
            resp = await client.post("/metrics/recompute", json=target, timeout=TIMEOUT_S)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
            if attempt == 0:
                await asyncio.sleep(RETRY_DELAY_S)
                continue
            return False
        if resp.status_code >= 500 and attempt == 0:
            await asyncio.sleep(RETRY_DELAY_S)
            continue
        return resp.status_code == 200
    return False


async def _with_jitter(target: dict, client: httpx.AsyncClient, sem: asyncio.Semaphore) -> bool:
    async with sem:
        if JITTER_MS > 0:
            await asyncio.sleep(random.uniform(0, JITTER_MS / 1000))
        return await recompute_one(client, target)


async def run() -> RunSummary:
    base_url = os.environ["API_BASE_URL"]
    secret = os.environ["INTERNAL_CRON_SECRET"]

    started = time.monotonic()
    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {secret}"},
        timeout=TIMEOUT_S,
    ) as client:
        targets = await fetch_targets(client)
        sem = asyncio.Semaphore(CONCURRENCY)
        results = await asyncio.gather(
            *(_with_jitter(t, client, sem) for t in targets),
            return_exceptions=False,
        )

    succeeded = sum(1 for ok in results if ok)
    return RunSummary(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        duration_s=time.monotonic() - started,
    )


def main() -> int:
    if not os.environ.get("API_BASE_URL") or not os.environ.get("INTERNAL_CRON_SECRET"):
        print("API_BASE_URL and INTERNAL_CRON_SECRET must be set", file=sys.stderr)
        return 1
    try:
        summary = asyncio.run(run())
    except (httpx.HTTPError, KeyError) as exc:
        print(f"enumeration failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"recompute_run_complete total={summary.total} succeeded={summary.succeeded} "
        f"failed={summary.failed} duration_s={summary.duration_s:.1f}"
    )
    return 0
```

Note the two distinct failure modes:

- **Scheduler-level failure** (no `API_BASE_URL`, enumeration raises) → `exit 1`.
- **Per-repo failure** (non-2xx on `/metrics/recompute`) → logged in `failed` count, `exit 0`.

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd server && poetry run pytest tests/test_run_hourly_recompute.py -x -v
```

Expected: all seven tests pass.

- [ ] **Step 3: Run the full server test suite**

```bash
cd server && poetry run pytest -x -q
```

Expected: all tests pass.

- [ ] **Step 4: Lint & type-check**

```bash
cd server && poetry run ruff check scripts/run_hourly_recompute.py tests/test_run_hourly_recompute.py
cd server && poetry run mypy scripts/run_hourly_recompute.py
```

- [ ] **Step 5: Commit**

```bash
git add server/scripts/run_hourly_recompute.py
git commit -m "feat: implement hourly batch metrics recompute scheduler"
```

---

## Chunk 3: Railway Config & Docs

### Task 5: Add Railway cron config

**Files:**
- Create: `server/railway.toml`

- [ ] **Step 1: Create `server/railway.toml`**

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "poetry run python scripts/run_hourly_recompute.py"
cronSchedule = "0 * * * *"
restartPolicyType = "never"
```

- [ ] **Step 2: Commit**

```bash
git add server/railway.toml
git commit -m "chore: add Railway cron config for hourly metrics recompute"
```

---

### Task 6: Update documentation

**Files:**
- Modify: `server/README.md`
- Modify: `docs/prds/012 - Scheduled Infrastructure.md` (add cross-link to RFC 018)
- Modify: `README.md` (brief mention)

- [ ] **Step 1: Document the endpoint and script in `server/README.md`**

Add a "Scheduled Metrics" section covering:

- The two internal endpoints (`POST /metrics/recompute`, `GET /metrics/recompute-targets`).
- The scheduler script location and env var contract.
- How to invoke it locally against the dev server.

- [ ] **Step 2: Cross-link from PRD 012**

At the bottom of `docs/prds/012 - Scheduled Infrastructure.md`, add:

```markdown
---

**Implemented by:** [RFC 018 — Batch Metrics Scheduling](../rfcs/018-batch-metrics-scheduling.md)
```

- [ ] **Step 3: One-line mention in root `README.md`**

Under the existing features / architecture overview, mention hourly metric refresh via Railway cron.

- [ ] **Step 4: Commit**

```bash
git add server/README.md docs/prds/012\ -\ Scheduled\ Infrastructure.md README.md
git commit -m "docs: document hourly metrics recompute scheduler"
```

---

### Task 7: Local end-to-end smoke test

This is a **manual** validation step — not a new test file.

- [ ] **Step 1: Prepare a local DB with seed data**

```bash
cd server && make seed-reset && make seed
```

- [ ] **Step 2: Start the server with a known cron secret**

```bash
cd server && INTERNAL_CRON_SECRET=local-cron-secret poetry run uvicorn app.main:app --reload
```

- [ ] **Step 3: In another terminal, run the scheduler against localhost**

```bash
cd server && \
  API_BASE_URL=http://localhost:8000 \
  INTERNAL_CRON_SECRET=local-cron-secret \
  PYTHONPATH=. poetry run python scripts/run_hourly_recompute.py
```

- [ ] **Step 4: Verify via psql that `metrics_refresh_log` populated**

```sql
SELECT tenant_id, repo_id, status, completed_at
FROM metrics_refresh_log
WHERE hour >= date_trunc('hour', now())
ORDER BY completed_at DESC;
```

Expect one row per seeded repo, all `status = 'success'`.

- [ ] **Step 5: Verify the dashboard reflects fresh metrics**

Open the client at `http://localhost:5173`, confirm deployment frequency / lead time / cycle time / throughput all show recent data.

---

### Task 8: Production smoke test & Railway cron enablement

Manual steps — **do not put these in code**.

- [ ] **Step 1:** With production `API_BASE_URL` and `INTERNAL_CRON_SECRET` (via `railway run` or a scoped shell), invoke the script once manually against production. Confirm exit 0 and the `metrics_refresh_log` rows appear.
- [ ] **Step 2:** Create the new Railway cron service pointed at the `server/` directory. Verify Railway picks up `railway.toml` (cron schedule visible in the service dashboard).
- [ ] **Step 3:** Set `API_BASE_URL` and `INTERNAL_CRON_SECRET` as service env vars.
- [ ] **Step 4:** Wait for the next hourly tick. Confirm the Railway run history shows a successful run, and `metrics_refresh_log` has matching entries.
- [ ] **Step 5:** Observe for 48h. If exit codes start failing, open a follow-up fix.
