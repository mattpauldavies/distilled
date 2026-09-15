# GitHub Ingest and Deployment Detection

**Status:** Shipped
**Consolidates:** PRD 001, RFC 001 (deployment detection), RFC 020 (GitHub API reliability), RFC 023 (installation/repository lifecycle), RFC 024 (production environment detection)

## Summary

Detect production deployments from GitHub Environments, ingest pull requests, and
link the two. This is the foundation every DORA metric rests on, so the bar is
explainability: a user must be able to see why a deployment was counted and which
PRs were attributed to it.

## Goals

- Detect production deployments with high confidence, using GitHub Environments.
- Ingest the full PR lifecycle so both delivery and work-in-progress metrics are possible.
- Link PRs to deployments with measurable coverage.
- Survive transient GitHub failures without losing an installation sync.

## Non-goals

- Incidents, MTTR, and change failure rate — see [009 Reliability Metrics](009-reliability-metrics.md).
- Storing raw webhook payloads.
- A queue-backed ingest pipeline with retries and a dead-letter queue.

## Definitions

**Production environment** — a GitHub Environment whose name contains `prod` or `live`
(case-insensitive substring), or one a user has marked production via
`PATCH /environments/{id}`. Classification happens once, when the environment is first
discovered, and is persisted on `environments.is_production`.

**Production deployment event** — recorded when a `deployment_status` webhook arrives with
`state == "success"` for an environment marked production. De-duplicated on GitHub's
`deployment_id`.

## Design

### Ingest path

A single receiver, `POST /webhooks/github`, verifies the HMAC-SHA256 signature, records the
delivery, returns 200, and dispatches to handlers via FastAPI `BackgroundTasks`. Payloads
are parsed into domain rows inline — nothing raw is stored.

| Event                      | Action                                                        |
| -------------------------- | ------------------------------------------------------------- |
| `installation`             | Upsert the installation, sync repos, discover environments     |
| `installation_repositories`| Add or soft-remove repos across every linked workspace         |
| `deployment_status`        | On success in a production environment, record a deployment    |
| `pull_request`             | Upsert the PR on open, draft toggle, reopen, close, and merge  |

The domain model, service names, and fan-out semantics are described in
[architecture.md](../architecture.md); this proposal records why they are shaped that way.

### PR to deployment attribution

A PR is attributed to the first production deployment that follows its merge: PRs with
`merged_at` between the previous deployment and the current one, restricted to PRs
targeting the repo's default branch. The first deployment in a repo uses a 30-day lookback
as its lower bound. Attribution rows are inserted `ON CONFLICT DO NOTHING`, so replaying a
delivery is safe.

This is a heuristic, not commit ancestry. It was chosen because it needs no extra GitHub
calls and is trivially explainable — the alternative (walking SHA ancestry) is more precise
but costs an API round trip per deployment and is harder to show a user.

### GitHub API reliability

`GitHubClient` routes every outbound call through one retry helper rather than decorating
each method:

- Four attempts, exponential backoff with full jitter, ~20s worst-case wall clock.
- Retried on transport errors, read timeouts, and HTTP 429, 502, 503, 504.
- Never retried on other 4xx — those are caller or permission problems.
- `Retry-After` and `x-ratelimit-reset` are preferred over the exponential schedule when
  GitHub supplies them, capped at 30s per attempt.
- A 401 on a call carrying an installation token evicts that token from the cache and
  retries **once**, outside the backoff loop, so a genuinely revoked installation surfaces
  immediately rather than as a slow retry.

This matters most on a fresh install: an org with a hundred repos means a hundred
sequential `list_environments` calls, and before this change one rate-limit response
aborted the whole installation with no resume path.

### Webhook delivery record

`webhook_events` records one row per accepted delivery, keyed on the `X-GitHub-Delivery`
header (unique, so GitHub's own retries are a no-op). The route inserts the row with
`status = 'received'` in its own transaction **before** scheduling the dispatch, and the
dispatcher updates it to `succeeded`, `failed`, `skipped`, or `no_handler` afterwards in a
separate transaction. The separate transactions are the point: a receipt must survive the
handler's rollback, and rows stuck in `received` are how we detect a dead dispatcher.

Deliveries rejected before dispatch (bad HMAC, oversized body, wrong content type) are not
recorded — they never had a chance to be processed, and recording them would be noise.

The table holds the delivery metadata and body size, never the body itself; storing
payloads would raise a retention and PII question we have no need to answer yet.

### Repository lifecycle

Repos and installations are soft-deleted with a nullable `removed_at`, never hard-deleted.
Historical PRs, deployments, environments, and metrics are exactly what the product exists
to report on, and a hard delete would either destroy them or violate foreign keys.
Re-adding a repo, or re-installing the App, clears `removed_at` through the existing
upserts, so resurrection is free.

Only `GET /repos` filters soft-deleted rows. Ingest lookups and the repo middleware do not:
historical data stays reachable by direct navigation, and GitHub stops delivering events
for removed repos anyway.

## Decisions

**`deployment_status` over `workflow_run`.** The event carries the environment natively, so
no extra API call is needed per run.

**No raw payload storage.** Structured domain rows plus a delivery record answer every
operator question we have had, and scale better than keeping every payload.

**Immutable deployment events.** Events are facts; there is no `updated_at`.

**Composite primary key on attribution.** `(deployment_id, pr_id)` enforces "attributed at
most once" naturally, with no extra constraint.

**Substring matching for production environments, deliberately greedy.** An anchored regex
stored `distilled / production`, `prod-eu`, and `web:live` as non-production, and their
deployments were then silently skipped — invisible to the user and biasing DORA metrics
downward. Substring matching also catches `preprod` and `staging-prod-mirror`, which is the
accepted trade: an over-counted environment is visible in the deployment list and
correctable, whereas a missed one is not visible at all. No deny-list was added — that
would reintroduce exactly the guessing this removed.

**Classification at discovery, not per deployment.** Ingest reads a stored boolean, keeping
the classifier off the webhook hot path.

**No circuit breaker, no retry queue.** One outbound dependency and bounded attempts make a
breaker unnecessary, and a queue runtime conflicts with the no-in-process-schedulers rule.
The `webhook_events` table is the foundation for replay if we ever need it.

## Known limitations

- **At-most-once webhook processing.** `BackgroundTasks` is in-process; a crash mid-dispatch
  loses the event, and GitHub will not retry because we already returned 200. The receipt
  row and GitHub's Recent Deliveries UI are the recovery path — see
  [the redelivery runbook](../runbooks/webhook-redelivery.md).
- **Environments are only discovered at install time.** An environment created on an
  already-connected repo is never discovered, so its deployments are skipped. Re-running the
  connect flow is currently the only refresh.
- **The `is_production` override has no UI.** `PATCH /environments/{id}` exists but has no
  client consumer, so correcting a misclassification needs a raw API call.
- **30-day lookback on first deployment.** PRs merged earlier are never attributed.

## Deferred

Async webhook processing with retry and a dead-letter queue; a shared multi-worker token
cache; payload storage and an admin replay surface; scheduled detection of stuck deliveries.

## History

- **PRD 001 / RFC 001** established the domain model, webhook infrastructure, detection, and
  the attribution heuristic.
- **RFC 020** added the retry layer, 401 token refresh, and the `webhook_events` table.
- **RFC 023** added `installation_repositories` handling and `installation.deleted`, with
  soft-delete semantics.
- **RFC 024** relaxed environment detection from exact match to substring, with a backfill
  migration.
- **RFC 026** made ingest fan out to every workspace tracking a repo — see
  [004 Accounts and Workspaces](004-accounts-and-workspaces.md).
