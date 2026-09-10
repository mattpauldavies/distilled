# Server

FastAPI backend for deployment detection and DORA metrics. Ingests GitHub webhooks, detects production deployments, and attributes PRs to deployments.

## Setup

```sh
cp .env.example .env  # edit as needed
poetry install
make db-up            # start Postgres
make migrate          # apply migrations
```

## Run

```sh
poetry run uvicorn app.main:app --reload --port 8000
```

## API docs

http://localhost:8000/docs (Swagger UI) or http://localhost:8000/redoc

## Structure

```
app/
  main.py          # App factory, lifespan, router registration
  config.py        # Settings via pydantic-settings (.env)
  logging.py       # Dev-mode file logging setup
  db.py            # Async SQLAlchemy engine + session factory
  models/          # ORM models (database tables)
  schemas/         # Pydantic request/response shapes (API contract)
  routes/          # FastAPI routers (HTTP layer)
  services/        # Business logic (webhook handling, GitHub API, attribution)
  middleware/      # Request-scoped context via FastAPI dependencies (tenant, repo)
database/          # Alembic migrations
```

## Environment variables

| Variable                  | Description                              | Default                                                             |
| ------------------------- | ---------------------------------------- | ------------------------------------------------------------------- |
| `DATABASE_URL`            | Async Postgres connection string         | `postgresql+asyncpg://distilled:distilled@localhost:5432/distilled` |
| `GITHUB_APP_ID`           | Numeric GitHub App ID                    | —                                                                   |
| `GITHUB_PRIVATE_KEY_PATH` | Path to `.pem` private key file          | —                                                                   |
| `GITHUB_WEBHOOK_SECRET`   | Webhook secret from GitHub App settings  | —                                                                   |
| `SEED_TENANT_ID`          | Dev tenant UUID                          | `00000000-0000-0000-0000-000000000001`                              |
| `SEED_TENANT_NAME`        | Dev tenant name                          | `dev`                                                               |
| `ENVIRONMENT`             | `development` enables local file logging | `production`                                                        |
| `INTERNAL_CRON_SECRET`    | Bearer token for scheduled recompute     | —                                                                   |
| `FORWARDED_ALLOW_IPS`     | Upstream addresses uvicorn trusts `X-Forwarded-For` from (read by uvicorn, not `Settings`). Set to `*` behind a trusted proxy — see [Rate limiting](#rate-limiting) | `127.0.0.1` |
| `CLERK_JWKS_URL`          | Clerk JWKS endpoint for JWT verification | — (required in production)                                          |
| `CLERK_PUBLISHABLE_KEY`   | Clerk publishable key (for reference)    | —                                                                   |
| `GITHUB_APP_SLUG`         | GitHub App slug for install links        | —                                                                   |
| `EMAIL_BASE_URL`          | Public URL of the frontend (for invite accept links) | `http://localhost:5173`                                  |
| `EMAIL_PROVIDER`          | `log` (dev) or `resend` (prod)           | `log`                                                               |
| `RESEND_API_KEY`          | Resend API key (required when `EMAIL_PROVIDER=resend`) | —                                                       |
| `EMAIL_FROM`              | RFC 5322 from address for invitations    | —                                                                   |
| `INVITATION_TTL_DAYS`     | Days before a pending invitation expires | `14`                                                                |

## API endpoints

| Method | Path                            | Description                                                     |
| ------ | ------------------------------- | --------------------------------------------------------------- |
| GET    | `/health`                       | Health check                                                    |
| POST   | `/webhooks/github`              | GitHub webhook receiver (HMAC verified)                         |
| GET    | `/repos`                        | List repos for tenant (paginated)                               |
| GET    | `/environments`                 | List environments (optional `?repo_id=`)                        |
| PATCH  | `/environments/{env_id}`        | Toggle `is_production`                                          |
| GET    | `/deployments`                  | List deployments (requires `repo_id`, filter: env, date range)  |
| GET    | `/deployments/{id}`             | Deployment detail + attributed PRs                              |
| GET    | `/pull-requests`                | List PRs (requires `repo_id`, filter: date range)               |
| GET    | `/pull-requests/{id}`           | PR detail + linked deployment                                   |
| POST   | `/metrics/recompute`            | Trigger per-repo metric recompute (Bearer auth)                 |
| GET    | `/metrics/deployment-frequency` | Deployment frequency (daily counts, 30/90/180 day window)       |
| GET    | `/metrics/lead-time`            | Lead time percentiles (weekly, 30/90/180 day window)            |
| GET    | `/metrics/pr-cycle-time`        | PR cycle time percentiles (weekly, 30/90/180 day window)        |
| GET    | `/metrics/throughput`           | PR merge throughput (weekly counts, 30/90/180 day window)       |
| GET    | `/metrics/open-prs`             | Open PR counts (total, live, draft)                             |
| GET    | `/metrics/pr-ageing`            | PR age distribution (<2d, 2-7d, 7-14d, >14d buckets)            |
| GET    | `/metrics/data-quality`         | Attribution coverage + freshness + production-env setup         |
| GET    | `/team`                         | Team members + pending invitations (owner only)                 |
| PATCH  | `/team`                         | Rename tenant / dismiss rename prompt (owner only)              |
| DELETE | `/team`                         | Delete tenant (sole-user owner only)                            |
| POST   | `/team/invitations`             | Create invitation (owner only)                                  |
| POST   | `/team/invitations/{id}/resend` | Re-issue token + email (owner only)                             |
| DELETE | `/team/invitations/{id}`        | Revoke pending invitation (owner only)                          |
| DELETE | `/team/members/{user_id}`       | Remove member (owner only)                                      |
| POST   | `/team/members/{user_id}/transfer` | Transfer ownership (owner only)                              |
| POST   | `/team/leave`                   | Leave tenant (members only)                                     |
| GET    | `/me/tenants`                   | List the user's memberships (no X-Tenant-Id required)           |
| GET    | `/me/invitations`               | List pending invitations matching verified Clerk emails         |
| POST   | `/me/invitations/{id}/accept`   | Banner-accept a pending invitation                              |
| POST   | `/me/invitations/{id}/decline`  | Dismiss a pending invitation                                    |
| POST   | `/me/active-tenant`             | Persist the user's switcher choice                              |
| POST   | `/invitations/redeem`           | Token-based redeem (JWT only)                                   |
| POST   | `/internal/invitations/expire`  | Janitor: revoke expired invitations (cron secret)               |

## Scheduled metrics

Metric aggregation runs hourly for every `(tenant, repo)` pair. The server exposes two internal endpoints (Bearer-authenticated with `INTERNAL_CRON_SECRET`):

- `GET /metrics/recompute-targets` — returns every `(tenant_id, repo_id)` pair.
- `POST /metrics/recompute` — recomputes all four metrics for one repo; idempotent per hour.
  Rate limited to `1000/hour` rather than per minute: the fan-out is one call per repo in a
  single hourly burst, so a per-minute cap throttled the job against itself.

A standalone script, [`scripts/run_hourly_recompute.py`](scripts/run_hourly_recompute.py), enumerates targets and fans out per-repo recompute calls with bounded concurrency and small jitter. It exits `1` on scheduler-level failure (missing config, enumeration unreachable) and `0` otherwise — per-repo failures are surfaced in `metrics_refresh_log`.

Run locally against a dev server:

```sh
API_BASE_URL=http://localhost:8000 \
INTERNAL_CRON_SECRET=<secret> \
PYTHONPATH=. poetry run python scripts/run_hourly_recompute.py
```

In production the script is invoked by a dedicated Railway cron service (configured in the Railway dashboard, separate from the `server` web service) on the schedule `0 * * * *` (UTC).

Optional tuning env vars (script-only): `RECOMPUTE_CONCURRENCY` (default `3`), `RECOMPUTE_JITTER_MS` (default `2000`), `RECOMPUTE_TIMEOUT_S` (default `120`). See [RFC 018](../docs/rfcs/018-batch-metrics-scheduling.md) for the full design.

## Logging

All logs go to **stdout**. This matters on Railway, which classifies anything a container
writes to stderr as `level.error` regardless of the record's own level — a bare
`logging.StreamHandler()` defaults to stderr, which made every `INFO` line arrive in the
log explorer coloured red and buried genuine failures. See
[ADR 008](../docs/adrs/008-structured-production-logging.md).

**In production**, each record is one JSON line in Railway's field contract:

```json
{"message": "attributed 1 PRs to deployment=397bb8f3", "level": "info", "logger": "app.services.attribution_service", "timestamp": "2026-09-10T11:57:30.360000+00:00"}
```

Railway reads `message` as the log text and `level` as the severity, and exposes the
remaining keys as attributes you can filter on — `@level:error` for real failures,
`@logger:app.services.invitation_service` to follow one module. Exceptions add a rendered
`exception` field.

**In development** (`ENVIRONMENT=development`), the console keeps the human-readable
`%(asctime)s %(levelname)s %(name)s: %(message)s` format and logs are additionally written
to `logs/dev.log`, truncated on each restart. The `logs/` directory is gitignored.

`httpx` and `httpcore` are pinned to `WARNING`: they log one `INFO` line per outbound
request, so every Clerk lookup and GitHub call would otherwise produce a log line we did
not ask for. Uvicorn's own loggers are reparented onto the root handler so the whole
process emits one consistent stream.

## Rate limiting

`slowapi` applies a `200/minute` default to every route, with tighter per-route limits on
webhooks and the internal cron endpoints. Limits are keyed on the client IP via
`request.client.host`.

**Behind a proxy this needs `FORWARDED_ALLOW_IPS`.** Uvicorn only rewrites
`request.client.host` from `X-Forwarded-For` when the immediate peer is listed in
`forwarded_allow_ips`, which defaults to `127.0.0.1`. A platform proxy is never
`127.0.0.1`, so without this variable every public request keys on the *proxy's* address
and the whole user base shares one bucket. Set `FORWARDED_ALLOW_IPS=*` on Railway, where
the container port is reachable only through Railway's edge. Do **not** set it where the
container is directly reachable: a client could then spoof the header and evade limits.

`POST /metrics/recompute` is limited per *hour*, not per minute, because the hourly job
fans out one call per repository — see [Scheduled metrics](#scheduled-metrics).

## Webhook events

| Event                                          | Trigger                  | Action                                                     |
| ---------------------------------------------- | ------------------------ | ---------------------------------------------------------- |
| `installation` (created)                       | App installed            | Upsert installation, sync repos, discover environments     |
| `installation` (deleted)                       | App uninstalled          | Soft-delete installation and its repos (`removed_at`)      |
| `installation_repositories` (added)            | Repos added to install   | Upsert repos, discover environments, clear `removed_at`    |
| `installation_repositories` (removed)          | Repos removed from install | Soft-delete listed repos (`removed_at`)                  |
| `deployment_status` (success)                  | Deployment succeeds      | Create deployment event if production environment          |
| `pull_request` (opened, reopened, closed, ...) | PR lifecycle event       | Upsert PR record (capture draft, closed_at status)         |

Repositories and installations are never hard-deleted: removal stamps
`removed_at` so historical PRs, deployments, and metrics stay intact, and
re-adding a repo (or re-installing the App) clears the stamp. `GET /repos`
excludes soft-deleted repos. See
[RFC 023](../docs/rfcs/023-installation-repository-lifecycle.md).

### Webhook delivery audit (`webhook_events`)

Every accepted delivery is recorded in the `webhook_events` table with one of
five statuses: `received`, `succeeded`, `failed`, `skipped`, `no_handler`. A
delivery is `skipped` when every handler deliberately did nothing — an unknown
repo or installation, or an action we don't process — so silent drops are
distinguishable from real work. If any handler fails, `failed` wins. The route
inserts the row in its own transaction immediately after HMAC + content-type
checks pass; the dispatcher updates it once handlers complete. Receipt and
outcome use separate sessions so the audit row survives any handler rollback.
Webhooks rejected before dispatch (bad HMAC, malformed body, missing
`X-GitHub-Delivery`) are not recorded.

When an event appears to have been missed or failed processing, see
[`docs/runbooks/webhook-redelivery.md`](../docs/runbooks/webhook-redelivery.md)
for triage queries and how to use GitHub's Recent Deliveries UI to redeliver.

## GitHub API retries

Outbound calls in `app/services/github_client.py` go through a `tenacity`-driven
retry helper: up to 4 attempts with exponential backoff and jitter
(1s → 8s) on `httpx` transport errors and HTTP 429 / 502 / 503 / 504. When
GitHub returns a `Retry-After` header (or `x-ratelimit-reset` for secondary
rate limits on 403), the server-supplied delay is honoured up to a 30s cap.

Installation tokens are cached in-process for ~1 hour. On a 401 against an
authenticated call the cached token is evicted and the request is retried
once with a freshly-minted token; a second 401 surfaces normally.

## Deployment

The server ships as a container (`server/Dockerfile`), matching the client and
website. Building explicitly means the platform never has to guess a Python
toolchain — Railway's Railpack builder installs interpreters through `mise`,
and recent `mise` releases refuse any python-build-standalone release without a
GitHub build attestation, which fails the build for older 3.12 patches.

```sh
docker build -t distilled-server server/
docker run --rm -p 8000:8000 --env-file server/.env distilled-server
```

The image runs `uvicorn app.main:app` on `$PORT` (default `8000`) as a
non-root user. Python is pinned to the same patch release in the `Dockerfile`
and in `server/.python-version`; bump both together.

On Railway, set the service's root directory to `server/` so the `Dockerfile`
is detected, supply the environment variables above, and run migrations as the
deploy's release/pre-deploy command:

```sh
alembic upgrade head
```

Set `FORWARDED_ALLOW_IPS=*` on the web service so rate limits key on the real
client IP rather than Railway's edge proxy — see [Rate limiting](#rate-limiting).

## Testing

```sh
make test              # run all tests
make test-coverage     # show coverage report
```

See [RFC 003: Better Python Tests](../docs/rfcs/003-better-python-tests.md) for architecture details.

## Linting and formatting

```sh
make lint-server       # ruff check + mypy
make format-server     # ruff format (auto-fix style)
```

Tools and configuration (all in `pyproject.toml`):

| Tool   | Purpose                   | Config key       |
| ------ | ------------------------- | ---------------- |
| `ruff` | Lint + format             | `[tool.ruff]`    |
| `mypy` | Static type checking      | `[tool.mypy]`    |

Ruff enforces E, F, I (import sort), UP (pyupgrade), and B (bugbear) rules at 120-char line length. Auto-generated migration files (`database/`) are excluded. `mypy` runs with `disallow_untyped_defs = true` — all functions must have type annotations.
