# Architecture

## Overview

Distilled is a two-tier web app: a FastAPI backend that ingests GitHub webhooks and serves a REST API, and a React frontend that displays engineering metrics.

```
GitHub webhook ──► FastAPI ──► PostgreSQL
                      ▲
                      │
                   React UI
```

## Backend (server/)

### Layers

| Layer        | Directory           | Responsibility                                            |
| ------------ | ------------------- | --------------------------------------------------------- |
| Routes       | `app/routes/`       | HTTP handling, request/response serialization             |
| Services     | `app/services/`     | Business logic, GitHub API, webhook processing            |
| Models       | `app/models/`       | SQLAlchemy ORM, database schema, shared query predicates  |
| Schemas      | `app/schemas/`      | Pydantic validation, API contracts                        |
| Middleware   | `app/middleware/`   | Request-scoped context via FastAPI dependencies (tenant, repo) |

Note `app/middleware/` holds per-route FastAPI dependencies; cross-cutting ASGI middleware (CORS, security headers, rate limiting) lives in `app/main.py`.

Conventions the layers follow are recorded as ADRs: transaction ownership in
[ADR 003](adrs/003-transaction-boundaries.md), query placement in
[ADR 004](adrs/004-query-placement-and-domain-predicates.md).

### Key services

- **webhook_service** — HMAC signature verification, event handler registry, payload parsing helpers
- **github_client** — JWT auth, installation token management, GitHub API wrapper
- **ingest_installation_service** — handles app installation lifecycle (install, uninstall, repos added/removed), repo sync with soft delete, environment discovery
- **ingest_deployment_service** — processes deployment_status events
- **ingest_pr_service** — processes pull_request events into the PullRequest table
- **attribution_service** — links merged PRs to deployments via time-window heuristic
- **environment_service** — auto-detects production environments by name pattern: any name
  containing `prod` or `live` (case-insensitive substring, so `distilled / production` and
  `prod-eu` both qualify). Classification happens once, at discovery; `PATCH /environments/{id}`
  overrides it

### Metrics service delineation

Metrics are split across three services by **computation pattern**, not data source:

- **batch_metrics_service** — scheduled batch recompute (write side), results persisted to
  dedicated tables; also writes the `MetricsRefreshLog` row for each run
- **read_metrics_service** — the whole read side: live queries, reads over the pre-computed
  tables, and the dashboard section builders the `/metrics/*` routes serve
- **read_data_quality_service** — monitoring/observability of the metrics pipeline itself

Service names carry a role prefix: `ingest_*` consume webhook events (write side),
`batch_*` run on the scheduler (write side), `read_*` serve queries. Unprefixed modules
(`webhook_service`, `attribution_service`, `environment_service`, identity services,
`github_client`, `pagination`) are shared domain logic or infrastructure.

Note the weekly **chart series** are pre-computed, but the **headline numbers** (lead time
median, cycle time median, throughput summary) are live queries so they always reflect the
selected window exactly.

| Metric                          | Service      | Pattern             | Source Data       |
| ------------------------------- | ------------ | ------------------- | ----------------- |
| Deployment Frequency            | batch_metrics | pre-computed daily  | deployments       |
| Lead Time (weekly series)       | batch_metrics | pre-computed weekly | PRs + deployments |
| Lead Time (headline median)     | read_metrics  | live query          | PRs + deployments |
| PR Cycle Time (weekly series)   | batch_metrics | pre-computed weekly | PRs               |
| PR Cycle Time (headline median) | read_metrics  | live query          | PRs               |
| PR Throughput (weekly series)   | batch_metrics | pre-computed weekly | PRs               |
| PR Throughput (summary)         | read_metrics  | live query          | PRs               |
| Open PR Count                   | read_metrics  | live query          | PRs               |
| PR Ageing                       | read_metrics  | live query          | PRs               |
| Metrics Freshness               | read_data_quality | live query      | MetricsRefreshLog |
| Attribution Coverage            | read_data_quality | live query      | PRs + deployments |

The core "merged PRs on the default branch" and "open PRs" filters are defined once as
class-level predicates on the `PullRequest` model (`merged_on_branch`, `open_on_branch`)
and reused by every metric query.

**read_metrics_service** exposes one section builder per dashboard section; each of the `/metrics/*` endpoints delegates to its corresponding builder, so a metric's full read path (SQL through to response schema) lives in one module. The client fetches all sections in parallel, so one slow query never blocks the rest of the dashboard.

### Deployment

- The server, client and website are each built as a container; the platform runs the
  image rather than inferring a build. See
  [ADR 005](adrs/005-containerised-server-build.md).
- Database migrations run as an explicit release-phase command (`alembic upgrade head`),
  never from a container entrypoint.

### Scheduled jobs

- Scheduled jobs will be triggered via Railway Scheduled Jobs calling authenticated internal endpoints.
- Internal endpoints live in `app/routes/internal.py` with the cron-secret check applied at
  router level; user-facing routers get `require_auth` at router level in `main.py`.
- No in-process schedulers (e.g. APScheduler).
- No OS-level cron.
- All scheduled work must be idempotent. (Jobs must be safe to run multiple times.)
- All scheduled endpoints must require internal authentication.
- The demo seed script (`scripts/seed_demo.py`) inserts raw rows only and derives metrics by
  calling the same recompute pipeline the scheduled job uses — demo numbers can never drift
  from the production algorithm.

### Data flow: webhook to deployment

1. GitHub sends `deployment_status` to `POST /webhooks/github`
2. HMAC signature verified against `GITHUB_WEBHOOK_SECRET`
3. Event dispatched to handler via `BackgroundTasks` (return 200 immediately)
4. Handler checks `state == "success"` and environment `is_production`
5. Creates `ProductionDeploymentEvent`
6. Attribution service links PRs merged since last deployment

### Multi-tenancy

All tables carry `tenant_id`. Membership is a many-to-many relationship in `tenant_users`, with a `(user_id, tenant_id, role)` row per membership and a partial unique index enforcing exactly one owner per tenant. `users.last_active_tenant_id` is a per-user default — the tenant a fresh sign-in resolves to in the absence of an explicit choice.

The active tenant for any given request is resolved as:

1. `X-Tenant-Id` header on the request, if present (membership verified at request time)
2. Otherwise, `users.last_active_tenant_id`
3. Otherwise, 409 — the user has no active tenant and the client must surface onboarding

`require_owner` is the dependency used for owner-only routes (`/team/*`); membership lookups use indexed columns and add a single join per authenticated request.

Tenant deletion is a single `DELETE FROM tenants WHERE id = ...`: every tenant-scoped FK (`repositories`, `pull_requests`, `deployment_events`, `tenant_users`, `invitations`, all metrics tables) carries `ON DELETE CASCADE`. ADR 002 documents the rationale.

## Frontend (client/)

React 19 + Vite + TypeScript + Tailwind. Calls the backend via `VITE_API_BASE_URL` (defaults to same origin in production).

## Database

PostgreSQL 16 via Docker. Async access via SQLAlchemy + asyncpg. Migrations managed by Alembic.

## Auth model

GitHub App authentication (not OAuth):

- Server generates JWT signed with App private key
- JWT exchanged for installation access tokens (cached, auto-refreshed)
- Token mint failures are triaged via
  [docs/runbooks/github-app-auth.md](runbooks/github-app-auth.md)
- Webhooks verified via HMAC-SHA256
