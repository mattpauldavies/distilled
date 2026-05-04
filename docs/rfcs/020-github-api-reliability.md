# RFC 020: GitHub API Reliability and Webhook Failure Alerting

**Branch:** `claude/github-api-reliability-clBgp`

---

## Summary

Two related reliability gaps in the ingest path:

1. **No retry policy on outbound GitHub API calls.** `GitHubClient` (`server/app/services/github_client.py`) calls `resp.raise_for_status()` directly with no handling of 429s, 5xx, or transient `httpx` transport errors. A single rate-limit hit during a fresh installation aborts the entire repo/environment sync.
2. **No alerting on webhook handler failures.** `_dispatch_event` (`server/app/routes/webhooks.py:16`) catches every handler exception and logs it. Sentry is initialised (`server/app/main.py:30`) so the error is captured, but no alert rule fires and there is no on-call signal that we silently dropped a `deployment_status` or `pull_request` event.

This RFC proposes a small `tenacity`-driven retry layer on `GitHubClient`, single-token-refresh on 401, a Sentry alert rule for webhook handler failures, and a runbook entry for using GitHub's built-in webhook redelivery when an event is missed.

---

## Background

### Today's GitHub API path

- `GitHubClient.__init__` builds a single `httpx.AsyncClient` with a 30s timeout and no transport-level retry.
- Three call sites: `get_installation_token`, `list_repos`, `list_environments`. All three call `resp.raise_for_status()`, so any non-2xx terminates the surrounding handler.
- `installation_service._handle_created` (`server/app/services/installation_service.py:80`) loops over every repo in a fresh install and calls `list_environments` per-repo. For an org with ~100 repos this is ~100 sequential GitHub calls — one rate-limit response (`429`, or `403` with `x-ratelimit-remaining: 0`) aborts the whole installation flow and leaves environments un-discovered. There is no resume.
- Installation tokens are cached in a module-level dict for ~1 hour. There is no eviction-on-401, so a token rotated mid-flight (rare, but observed during App key rotation or revocation) produces a permanent 401 until the cache entry naturally expires.

### Today's webhook path

- `POST /webhooks/github` verifies HMAC, parses JSON, returns `200`, and schedules `_dispatch_event` via FastAPI `BackgroundTasks`.
- `_dispatch_event` opens a session, runs each registered handler, commits on success, rolls back and logs on exception.
- Sentry is initialised when `SENTRY_DSN` is set. `logger.exception` is auto-captured by the Sentry SDK's logging integration, so handler failures **do** become Sentry issues.
- What is missing: an alert rule that pages someone, and a way to find out when a webhook **never arrived** (GitHub outage, Railway outage, our service 5xx-ing the webhook itself).

### Why this matters now

- We have no operator-facing dashboard for ingestion health. The first signal of "we missed a deployment" today would be a customer noticing.
- The retry gap is more likely to bite as we grow tenants — GitHub rate limits are per-installation, but list_environments fan-out scales linearly with repo count.

---

## Design Decisions

### 1. `tenacity`-based retry helper inside `GitHubClient`

Add `tenacity` as a dependency and wrap the three outbound calls in a single private helper, `_request_with_retry(method, path, **kwargs)`, rather than decorating each public method individually.

**Why a helper, not a decorator on each method:**
- All three call sites share the same retry policy — duplicating `@retry(...)` is noise.
- Keeps public method signatures unchanged so callers and tests don't move.

**Retry policy:**

| Aspect              | Value                                                  |
| ------------------- | ------------------------------------------------------ |
| Max attempts        | 4 (initial + 3 retries)                                |
| Backoff             | Exponential, base 1s, multiplier 2, cap 8s, full jitter|
| Retried on          | `httpx.TransportError`, `httpx.ReadTimeout`, HTTP 429, 502, 503, 504 |
| Not retried on      | 4xx other than 429 (caller bug or auth issue)          |
| Per-call total cap  | ~20s wall-clock worst case                             |

**`Retry-After` and `x-ratelimit-reset`:** if GitHub returns 429 or 403 (with rate limit), prefer the server-supplied delay over the exponential schedule — capped at 30s per attempt to bound the wait. Log a structured warning so we can see rate-limit pressure in Sentry breadcrumbs.

**Idempotency note:** all three current call sites are `GET`s and the `POST /app/installations/.../access_tokens` call is documented as idempotent (issuing a new token is the entire side effect, and we always overwrite the cache). Safe to retry.

### 2. Token-refresh-on-401

If `_request_with_retry` receives a 401 on a call carrying an installation token, evict the cache entry for that `installation_id` and retry once with a freshly minted token. Do this **once per call** (not as part of the exponential retry loop) to avoid masking a genuine permission revocation as a slow loop.

This is the only "smart" retry; everything else is dumb exponential backoff.

### 3. No circuit breaker, no in-process queue

We considered and rejected:
- **Circuit breaker (e.g. `pybreaker`):** scale doesn't justify it. We have one outbound dependency, and `tenacity`'s bounded attempts already prevent runaway calls.
- **Persistent retry queue (Celery / Arq):** would require new infra and conflicts with the "no in-process schedulers" rule from `architecture.md`. The webhook persistence option (deferred — see "Out of scope") is the cleaner long-term answer if we ever need it.

### 4. Webhook failure alerting via Sentry rules + runbook

**No code change for alerting itself.** Sentry already captures `logger.exception` calls from `_dispatch_event`. We add:

- A **Sentry alert rule** (configured in the Sentry UI, not in code) that fires on:
  - Any new issue tagged `logger:app.routes.webhooks` (handler crashes), OR
  - More than 5 events from that logger in a 5-minute window (burst detection).
- Routed to Slack via Sentry's existing integration. No PagerDuty until we have an on-call rotation.

### 5. Runbook for missed webhooks

Add `docs/runbooks/webhook-redelivery.md` covering:

- How to confirm "we missed an event" (e.g. data quality `attribution_coverage` drops, customer reports a deployment not showing).
- How to use GitHub's App **Advanced → Recent Deliveries** UI to inspect the last 30 days of deliveries.
- How to redeliver: filter by event type, check the response code we returned, click **Redeliver**.
- When **not** to redeliver (we already processed it — `on_conflict_do_nothing` and `on_conflict_do_update` make this safe, but call out the invariant).

This is the cheapest possible "replay" mechanism and it's already built — we just need to write it down.

---

## Scope

**In scope:**
- Add `tenacity` dependency.
- Add `_request_with_retry` helper to `GitHubClient`; route `get_installation_token`, `list_repos`, `list_environments` through it.
- 401-triggered token cache eviction + single retry.
- Honour `Retry-After` / `x-ratelimit-reset` on 429 and rate-limited 403.
- Tests covering: success, transient 503 retried to success, 429 with `Retry-After`, terminal 401 after one cache-evict retry, exhausted retries surfacing the original `httpx.HTTPStatusError`.
- New runbook: `docs/runbooks/webhook-redelivery.md`.
- README updates: `server/README.md` retry policy paragraph; cross-link the runbook.
- Sentry alert rule + Railway healthcheck path + Railway deploy notification (configured in dashboards, captured in this RFC + runbook for repeatability).

**Out of scope (deferred):**
- Distributed retry queue.
- Per-tenant rate-limit isolation (we share one App so this is already structurally fine).
- Replacing FastAPI `BackgroundTasks` with a real job runner — orthogonal concern.

## Schema Changes

**None.**

## Config Changes

- Add `tenacity = "^9.0.0"` (or current major) to `server/pyproject.toml`.
- No new env vars. The retry policy is constants in code — tunables can be promoted to settings later if we ever need to.

## Files Touched

- `server/app/services/github_client.py` — retry helper, token-refresh-on-401, route existing methods through helper.
- `server/pyproject.toml` + `server/poetry.lock` — add `tenacity`.
- `server/tests/services/test_github_client.py` (new or extend existing) — retry behaviour tests with `httpx` MockTransport.
- `docs/runbooks/webhook-redelivery.md` (new).
- `server/README.md` — short paragraph on retry policy + link to runbook.

## Observability

- Each retried attempt logs at `WARNING` with `event=github_retry`, `attempt=N`, `status=...`, `wait_s=...`. Exhausted retries log at `ERROR` and re-raise — Sentry picks up the exception via the existing logging integration.
- Token eviction logs at `INFO` with `event=installation_token_evicted`, `installation_id=...`.
- No new metrics. Sentry breadcrumbs + structured logs are enough at this stage; we can add a counter later if retry pressure becomes a recurring topic.

## Risks and Mitigations

| Risk                                                                                  | Mitigation                                                                                                                       |
| ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Retry loop masks a real GitHub outage by silently extending request latency.          | Bounded total wall-clock (~20s per call); structured logs on every retry; Sentry sees exhaustion.                                |
| Token-evict-and-retry on 401 hides a genuinely revoked installation as transient.     | Only **one** retry post-eviction; second 401 surfaces normally and Sentry catches it.                                            |
| Sentry alert is noisy on a flaky GitHub day.                                          | Use the burst rule (>5 in 5min) plus first-occurrence rule; tune threshold if it's chatty for the first week.                    |
| Railway healthcheck restarts the container during a long-running install sync.        | `/health` is a lightweight DB-free endpoint; install sync runs in a `BackgroundTask` and doesn't block the event loop. Low risk. |
| `Retry-After` of 60s blocks an event-loop slot for too long.                          | Cap honoured wait at 30s per attempt; beyond that we fail and let the caller decide (webhook handler will surface to Sentry).    |

---

## Implementation Plan

_To be appended to this RFC after design review and approval, per project convention (CLAUDE.md → "Spec location" / "Plan location")._
