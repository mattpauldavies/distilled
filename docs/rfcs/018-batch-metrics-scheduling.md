# RFC 018: Batch Metrics Scheduling

**Goal:** Reliably trigger hourly metric recomputes for every tenant + repo via a Railway scheduled job that fans out to the existing per-repo endpoint.

**Architecture:** A Railway cron runs a small Python script hourly. The script authenticates with `INTERNAL_CRON_SECRET`, asks the server for the current list of `(tenant_id, repo_id)` pairs, then POSTs to `/api/metrics/recompute` once per repo with small stagger and bounded concurrency. The existing endpoint already provides isolation, idempotency, and per-hour dedup via `metrics_refresh_log`.

**Tech Stack:** FastAPI, SQLAlchemy async, Railway cron, Python `httpx`, existing `pytest` suite.

---

## Background

- `POST /api/metrics/recompute` (`server/app/routes/metrics.py:61`) already computes all four metrics for a single `(tenant_id, repo_id)` and writes a refresh log entry (deduped on `(tenant_id, repo_id, hour)`).
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

- `GET /api/metrics/recompute-targets` → `{ "targets": [{ "tenant_id": "...", "repo_id": "..." }, ...] }`
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
- New enumeration endpoint `GET /api/metrics/recompute-targets`.
- New scheduler script `server/scripts/run_hourly_recompute.py`.
- Railway configuration (`railway.json` or `railway.toml`) defining the cron service and env vars.
- `APP_BASE_URL` config value so the script knows which deployment to target.
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

### `GET /api/metrics/recompute-targets`

- **Auth:** `Authorization: Bearer <INTERNAL_CRON_SECRET>`, validated with `hmac.compare_digest` (same helper as `/recompute`).
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
| `APP_BASE_URL`           | e.g. `https://distilled.up.railway.app`           |
| `INTERNAL_CRON_SECRET`   | Shared secret for the two internal endpoints      |
| `RECOMPUTE_CONCURRENCY`  | Worker count (default `3`)                        |
| `RECOMPUTE_JITTER_MS`    | Max jitter per call in ms (default `2000`)        |
| `RECOMPUTE_TIMEOUT_S`    | Per-call HTTP timeout in seconds (default `120`)  |

### Flow

```
1. Load config; fail fast if APP_BASE_URL or INTERNAL_CRON_SECRET missing.
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

Add a new **cron service** in Railway (separate from the web service) that runs:

```
poetry run python scripts/run_hourly_recompute.py
```

- **Schedule:** `0 * * * *` (top of every hour). PRD 012 says "hourly"; top-of-hour simplifies operator mental model.
- **Env vars:** `APP_BASE_URL`, `INTERNAL_CRON_SECRET`, plus the Python runtime vars the script needs.
- **No DB attachment needed** — the script only talks to the web API.

The exact Railway config file (`railway.json` vs `railway.toml`) will be chosen during implementation based on what Railway supports for cron services at the time of rollout.

## Config Changes

- Add `app_base_url: str = ""` to `server/app/config.py` (only used by scripts, but belongs in one place).
- Validate at script entry that it is non-empty — the web app itself does not require it.
- Add to `server/.env.example`: `APP_BASE_URL=`.

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

1. Merge endpoint + script + tests behind no feature flag (the script is dormant until Railway is configured).
2. Run the script manually against staging, verify `metrics_refresh_log` populates and dashboard metrics freshen.
3. Configure Railway cron in staging, let it run for at least 24h (24 hourly cycles).
4. Enable Railway cron in production.
5. Set up a simple alert on the Railway service: notify if exit code != 0 more than twice in 24h.

## Open Questions

1. Should `/recompute-targets` filter out tenants with zero deployments or zero PRs in the last 90 days to save cycles? (Default: no — keep the fan-out dumb and let the compute functions no-op cheaply.)
2. Do we want the script to publish a Prometheus-style summary, or is Railway log aggregation sufficient for now? (Default: logs only — consistent with PRD 012's "no distributed queue" stance.)
3. Should the run summary be persisted to a new `cron_run_log` table so the dashboard can show "last successful full refresh at T"? (Out of scope for this RFC; trackable via `max(completed_at)` on `metrics_refresh_log` in the interim.)

---

*Awaiting technical-design review before the implementation plan is appended.*
