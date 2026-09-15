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

---

## Release-based deployment tracking

**Status:** Proposed — design agreed, not yet built.

Deployment detection above assumes a team uses GitHub Deployments. Many don't: they ship
from a pipeline that never calls the Deployments API, or they version and publish releases
(libraries, SDKs, mobile and desktop apps, anything on a tagged cadence). For those teams
three of the four dashboard sections sit permanently in `setup_required`, and the only fix
Distilled offers is "change how you ship". The signal they already emit is a published
release, so read that instead.

### Design

**The source is chosen per repository**, not per workspace: a workspace typically holds
services that deploy and libraries that release, so one answer for both would be wrong for
half of them. `repositories.deployment_source` is `'deployment'` (default, today's
behaviour) or `'release'`, set by a workspace owner via `PATCH /repos/{repo_id}` from a new
**Settings → Deployment Tracking** page in the profile menu — a repo list with a
two-option control per row, following `RepositoriesPage`.

**Releases land in the existing `deployment_events` table.** A new
`ingest_release_service` handles `release` with action `published`, skipping drafts and
pre-releases, fanning out over the repo's workspaces exactly as `deployment_status` does
and skipping any whose source is not `'release'`. `handle_deployment_status_event` gains
the mirror-image skip. Both return `SKIPPED` when nothing matched, so a dropped delivery is
visible in `webhook_events` rather than silent. Attribution, metrics, the deployments list
and the batch jobs are untouched.

The same row, from each source — `acme/api` deploying to `production`, and `acme/sdk`
publishing `v2.4.0`:

| Column             | From `deployment_status`                                        | From `release.published`                                      |
| ------------------ | ---------------------------------------------------------------- | -------------------------------------------------------------- |
| `deployment_id`    | `1084312904` (`deployment.id`)                                   | `187463201` (`release.id`)                                     |
| `environment_name` | `production` (`deployment.environment`)                          | `release` (constant)                                           |
| `started_at`       | `2026-09-15T09:14:02Z` (`deployment.created_at`)                 | `2026-09-15T10:02:11Z` (`release.created_at`, the draft)       |
| `completed_at`     | `2026-09-15T09:18:47Z` (`deployment_status.created_at`)          | `2026-09-15T10:07:33Z` (`release.published_at`)                |
| `deployed_at`      | `2026-09-15T09:18:47Z` (same as `completed_at`)                  | `2026-09-15T10:07:33Z` (same as `completed_at`)                |
| `html_url`         | `…/acme/api/actions/runs/34988991322` (`deployment_status.target_url`) | `…/acme/sdk/releases/tag/v2.4.0` (`release.html_url`)    |
| `source`           | `deployment`                                                     | `release`                                                      |

Both `html_url` values go through `validate_github_url`, and `published_at` falls back to
`created_at` on the rare release that carries no publication time. Every other column —
`id`, `tenant_id`, `repo_id`, `created_at` — is filled the same way regardless of source,
and the rows are indistinguishable to attribution, the metrics jobs and the dashboard.

The same migration drops `ref` and `commit_sha` (see Decisions), so `GET /deployments` and
the deployment summary on `GET /pull-requests/{id}` stop returning them. Neither has a
client consumer.

`deployment_events.source` records what produced each row. Nothing filters on it: a repo
that ran on deployment events and then switched has one continuous history, which is what
an owner means by "switch". The unique constraint becomes
`(tenant_id, source, deployment_id)` — deployment IDs and release IDs are separate numeric
spaces sharing one column, and a collision would make a real deployment look like a
duplicate and drop it.

**The `setup_required` gate becomes source-aware.** The three sections in
`read_metrics_service` that require a production environment apply that requirement only
when `deployment_source == 'deployment'`. A published release *is* a production ship, and a
library repo has no environments to classify; without this, switching to releases would
record deployments the dashboard then refuses to show. `get_data_quality_section` reports
`deployment_source` so the client stops asking release-tracked repos for an environment.

### Decisions

**`release.published`, not `release.created`.** GitHub fires `created` when a **draft is
saved**, and does not fire it when that draft is later published — so every draft-first
workflow (release-drafter, semantic-release, or simply reviewing before publishing) would
record a deployment at draft time and nothing at ship time. `published` fires whenever a
release goes live, including one promoted from a draft. Pre-releases and drafts are
excluded; a pre-release promoted to GA fires `release.released`, which this design does not
handle.

**Contents: read is the cost of entry.** A GitHub App may only subscribe to the `release`
event if it holds [read access to Contents](https://docs.github.com/en/webhooks/webhook-events-and-payloads).
The gate is on *delivery*, not on reading anything — the payload is pushed to us, no API
call is involved — and it covers the event as a whole, so every action sits behind it.
GitHub has no separate Releases permission, and every alternative route to the same signal
(the Releases API, `push` with tag refs, the `create` tag event) is behind the same one.
The permission has been added to both App registrations. Installations must accept the
updated permission before release events are delivered.

**One source at a time, enforced at ingest.** A repo that both deploys and releases would
double count, and only its team knows which is real.

**`ref` and `commit_sha` are dropped from `deployment_events`.** Neither is read anywhere:
attribution is time-window based, no metric touches them, and the client never calls the
endpoints that serialise them. They also do not survive the second source — a release's
`target_commitish` is usually a branch name rather than the tag's commit, so `commit_sha`
would be empty on most release rows and populating it properly would cost an API round trip
per release for a field with no reader. Rather than carry two columns that mean different
things depending on the source, the migration drops both.

**`environment_name = "release"`.** The column stays and is `NOT NULL`. It is the only
per-row evidence of *why* a deployment was counted, which the greedy-substring decision
above explicitly leans on: `prod|live` also matches `preprod` and `staging-prod-mirror`,
and the environment name on the row is how an inflated count gets traced and corrected. A
fixed label for releases is honest; an empty string looks like a bug.

**No backfill, no recomputation on switch.** Consistent with deployment tracking, which has
never imported history. The new source counts from the next matching event; nothing is
deleted or recomputed.

### Accepted consequences

- Teams that both deploy and release under-count one of them. Intended, and the most likely
  source of "my numbers look low" questions.
- A repo switched to releases before its installation accepts the new permission looks
  identical to a quiet repo. The settings page says so; a "no release seen since you
  switched" signal in data quality would be the follow-up.
- Historic deployment rows and new release rows share one environment filter, where
  `release` sits alongside real environment names.

### Testing

Handler tests cover: published release recorded once per release-mode workspace; draft,
pre-release, non-`published` action, deployment-mode repo, and unknown repo each recording
nothing; redelivery staying idempotent; attribution running on the new row; and a repo
tracked by two workspaces in different modes producing exactly one row. `deployment_status`
gains its release-mode skip test. Metrics tests assert a release-mode repo with no
environments returns `ok` rather than `setup_required`. Per
[the query-testing rule](../../.claude/skills/server-query-tests/SKILL.md), the fan-out
lookups feed two rows through the mocked result.

### Delivery order

1. Migration and models (`deployment_source`, `source`, the new constraint).
2. `PATCH /repos/{repo_id}` with `deployment_source` on `RepoResponse`.
3. `ingest_release_service`, plus the skip in `ingest_deployment_service`.
4. Source-aware `setup_required` and data quality.
5. Settings → Deployment Tracking page and the profile-menu entry.
6. `github-app.md`, `metrics.md`, `architecture.md`, the runbooks and the READMEs.

### Deferred

`release.released` (pre-release promoted to GA), backfilling past releases from the API,
tag-push and `workflow_run` as sources, a workspace-level default for new repos, and
per-source breakdowns in metrics.
