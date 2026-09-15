# Metrics Engine

**Status:** Shipped
**Consolidates:** PRD 004 (multi-repo support), PRD 005 (aggregation engine), PRD 006 (deployment frequency), PRD 007 (lead time), PRD 008 (live metrics), PRD 009 (data quality), PRD 012 (scheduled infrastructure), RFC 004 (multi-repo), RFC 005–009, RFC 018 (batch scheduling)

## Summary

Turn ingested PRs and deployments into the metrics the dashboard shows. Heavy work
(percentiles, weekly series) is recomputed on a schedule and read from aggregate tables.
Light work (open PR counts, ageing buckets, headline medians) is queried live. Nothing
heavy is ever computed during webhook ingest or a dashboard request.

The metric definitions themselves are the product surface and live in
[metrics.md](../metrics.md). This proposal records how they are computed and why.

## Repo scoping

Everything is scoped to a `(workspace, repo)` pair. There is no cross-repo aggregation.

Four API rules follow from that, and apply beyond metrics:

- Prefer flat resource endpoints — `/deployments`, not `/repos/{id}/deployments`.
- At most two resources deep in a path.
- List endpoints require `repo_id`, validated by the shared `get_verified_repo` dependency,
  which 404s if the repo does not belong to the active workspace.
- Detail endpoints are workspace-scoped only. A redundant repo-ownership check buys nothing
  once workspace scoping already prevents cross-workspace leakage.

## Pre-computed versus live

The split is by **computation pattern**, not data source:

| Computed on a schedule                   | Computed live per request                    |
| ---------------------------------------- | -------------------------------------------- |
| Deployment frequency (daily buckets)     | Open PR count (live vs draft)                |
| Lead time (weekly median, P75, n)        | PR ageing buckets                            |
| PR cycle time (weekly median, P75, n)    | Headline medians for lead and cycle time     |
| PR throughput (weekly counts)            | Throughput summary                           |
|                                          | Attribution coverage and freshness           |

Weekly **series** are pre-computed because percentiles over a 180-day window are expensive.
The **headline numbers** are live so they reflect the selected window exactly rather than
the last complete week. The full delineation table is in
[architecture.md](../architecture.md).

Live queries target <100ms for a typical repo and rely on indexes over
`(tenant_id, repo_id, merged_at)`, `(tenant_id, repo_id, closed_at)`, and
`(tenant_id, repo_id, opened_at)`.

## Aggregate tables

Four bucket tables — `deployment_daily_metrics`, `lead_time_weekly_metrics`,
`pr_cycle_time_weekly_metrics`, `pr_throughput_weekly_metrics` — each unique on
`(tenant_id, repo_id, bucket)` and carrying an `algorithm_version`. Weeks start on Monday.

`metrics_refresh_log` records one row per repo per hour, unique on
`(tenant_id, repo_id, hour)`, with start and completion timestamps, status, and an error
message. It is both the freshness signal the dashboard reads and the per-repo failure record
the scheduler deliberately does not duplicate.

### Computation rules

- **Lead time** — `deployed_at - merged_at` for attributed PRs targeting the default branch,
  positive durations only, grouped by the deployment's week.
- **PR cycle time** — `merged_at - opened_at` for merged PRs targeting the default branch,
  grouped by merge week. `opened_at` is parsed from the webhook; the row's `created_at` is
  the insert timestamp and is not a substitute.
- **Throughput** — merged PRs per week.
- **Deployment frequency** — successful production deployments per day.

Every recompute covers the last 90 days, which spans all offered windows below 180 days;
longer windows read whatever buckets exist.

## Recompute

`POST /metrics/recompute` takes one `(tenant_id, repo_id)` pair, authenticated with
`INTERNAL_CRON_SECRET`. It and the enumeration endpoint below sit on a separate router with
the secret check applied at router level, but keep their `/metrics/*` paths because the
Railway cron service and the fan-out script pin them. The four metric functions run independently within the call, so one
failing does not stop the others, and the route commits and writes the refresh log.

There is deliberately **no bulk recompute endpoint**. One repo is one HTTP call, one
transaction, one refresh-log row. That isolates blast radius, makes staggering possible, and
keeps a single repo's failure from blocking the rest.

## Scheduling

A separate Railway cron service runs `scripts/run_hourly_recompute.py` at `0 * * * *`. It
asks `GET /metrics/recompute-targets` for the current `(tenant_id, repo_id)` list,
then fans out to the recompute endpoint with bounded concurrency (default 3) and 0–2s of
jitter per call. Each call has a 120s timeout and one retry after 5s on connection error or
5xx.

The scheduler holds no database credentials — it only talks to the API — so there is one
connection pool, one SSL policy, and one migration story. It also lives outside the web
process: no in-process scheduler, no "who owns the schedule" problem across instances, and
Railway's run history is first-class job observability.

Failure semantics are split on purpose:

- **Exit 1** — the scheduler could not enumerate targets or lost connectivity. This is what
  Railway alerts on.
- **Exit 0 with a failure count** — individual repos failed. Those are recorded in
  `metrics_refresh_log`, which is where per-repo state belongs.

Because the endpoint upserts per hour, re-running the scheduler within the same hour is
safe and produces the same result.

## Data quality

Three signals, computed live and surfaced in a deliberately low-prominence panel:

- **Attribution coverage** — attributed merged PRs over total merged PRs in the window.
  `null` when there are no merged PRs.
- **Freshness** — `max(completed_at)` over successful refresh-log rows. No rows means
  `no_data`; strictly more than two hours old means `stale`; exactly two hours is `ok`.
- **Setup configuration** — whether a production environment is configured, and which.

Metrics that depend on deployments return `setup_required` when no production environment
exists, rather than a misleading zero. Throughput, open PRs, and ageing do not depend on
deployments and always return data.

## Decisions

**UPSERT per bucket, not DELETE then INSERT.** Safer under partial failure, and retries
produce identical results.

**Percentiles in Python.** Fetch the durations for a week and compute median and P75 with
`statistics.median` and a sorted index. This avoids Postgres percentile extensions and keeps
the queries simple; the data volume per bucket does not justify anything cleverer.

**Granular buckets rather than pre-aggregated windows.** Daily and weekly rows are filtered
by date range at read time, so a 30-, 90-, and 180-day view share one set of rows instead of
triplicating storage.

**Hourly dedup on the refresh log.** Retries within an hour update the existing row, so
there are no duplicate entries and no inflated run counts.

**The fan-out stays dumb.** Targets are not filtered by recent activity — the compute
functions no-op cheaply on empty data, and the refresh-log row is still useful signal that
we tried.

**The recompute rate limit is expressed per hour.** The endpoint's legitimate traffic is one
burst of N calls once an hour, where N is the repo count. `10/minute` throttled the fan-out
against itself past ten repos, and the run still exited 0, so metrics went stale silently.
`1000/hour` fits the real traffic shape while still bounding a leaked cron secret to roughly
one fan-out per hour.

**Soft-deleted repos are excluded from recompute targets**, so removed repos stop consuming
the hourly budget.

## Deferred

A distributed job queue; exponential backoff on the scheduler; per-tenant scheduler
authentication; caching or incremental percentile updates; a dedicated `cron_run_log` table
(`max(completed_at)` over the refresh log already answers the question).

## History

- **PRD 004 / RFC 004** made `repo_id` required on list endpoints and introduced
  `get_verified_repo`.
- **PRD 005 / RFC 005** built the aggregate tables, compute functions, and the per-repo
  recompute endpoint.
- **PRD 006, 007 / RFC 006, 007** exposed deployment frequency and lead time as read
  endpoints. PRD 007 existed twice under two filenames with identical content.
- **PRD 008 / RFC 008** added the PR lifecycle columns (`is_draft`, `closed_at`, nullable
  `merged_at`) and the live open-PR and ageing endpoints.
- **PRD 009 / RFC 009** added the data-quality service.
- **PRD 012 / RFC 018** added the enumeration endpoint and the Railway cron fan-out.
- **RFC 022** moved the live headline aggregates out of the batch service and defined the
  read/batch/ingest naming — see [008 Engineering Practice](008-engineering-practice.md).
- **RFC 025** corrected the recompute rate limit.
