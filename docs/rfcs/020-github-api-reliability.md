# RFC 020: GitHub API Reliability and Webhook Failure Alerting

**Branch:** `claude/github-api-reliability-clBgp`

---

## Summary

Two related reliability gaps in the ingest path:

1. **No retry policy on outbound GitHub API calls.** `GitHubClient` (`server/app/services/github_client.py`) calls `resp.raise_for_status()` directly with no handling of 429s, 5xx, or transient `httpx` transport errors. A single rate-limit hit during a fresh installation aborts the entire repo/environment sync.
2. **No alerting on webhook handler failures.** `_dispatch_event` (`server/app/routes/webhooks.py:16`) catches every handler exception and logs it. Sentry is initialised (`server/app/main.py:30`) so the error is captured, but no alert rule fires and there is no on-call signal that we silently dropped a `deployment_status` or `pull_request` event.

This RFC proposes a small `tenacity`-driven retry layer on `GitHubClient`, single-token-refresh on 401, a new `webhook_events` table that records every delivery and its processing outcome, a Sentry alert rule for webhook handler failures, and a runbook entry for using GitHub's built-in webhook redelivery when an event is missed.

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
- **Persistent retry queue (Celery / Arq):** would require new infra and conflicts with the "no in-process schedulers" rule from `architecture.md`. The new `webhook_events` table (section 6) gives us a foundation for in-process replay later without bringing in a queue runtime.

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

### 6. Persist webhook deliveries to `webhook_events` (basic)

Today, the only record that a webhook ever arrived is a stdout log line. Once that line ages out we can't answer "did we receive the `deployment_status` for SHA abc?" or "what's our handler failure rate this week?". A small `webhook_events` table fixes both, with no new infrastructure.

**Scope of "basic":** record the delivery and its outcome. Nothing more. Specifically:

- **Yes:** insert one row per accepted webhook (after HMAC + content-type checks pass), update the row when the dispatch finishes, store error text on failure.
- **No:** no admin UI, no replay endpoint (GitHub's Recent Deliveries covers this), no automatic in-process retry on handler failure, no payload body storage (avoid the PII / disk-cost question for now — only the size).

**Write path:**

1. **Route inserts the row in its own transaction** (`status='received'`) **before** scheduling the background dispatch. This is intentional — if the dispatcher crashes or the worker is killed, the row still exists, and we can see "received but never completed" rows by querying `WHERE status='received' AND received_at < now() - interval '5 min'`.
2. **Dispatcher updates the row** (`status='succeeded' | 'failed' | 'no_handler'`, `processed_at`, `error_message`) in a separate transaction at the end of `_dispatch_event`. Update is keyed on `delivery_id`. If multiple handlers run for one event and one fails, status is `failed` and the error message is from the first failure (subsequent handlers still run — current behaviour is preserved).
3. **Webhooks rejected before dispatch** (HMAC fail, 413, 415, 400) are **not** recorded — those never had a chance to be processed and recording them would create noise. Sentry / access logs cover that case.

**Deduplication:** `delivery_id` (from the `X-GitHub-Delivery` header) is `UNIQUE`. A duplicate insert from GitHub retrying its own delivery is a no-op (`ON CONFLICT DO NOTHING`); the dispatcher's update on `delivery_id` still finds the original row. Manual GitHub redeliveries get a fresh `delivery_id` so they appear as new rows — that's correct, they are new deliveries from our perspective.

**Why row-per-receipt rather than row-per-handler-attempt:** today there is at most one handler per event type and `_dispatch_event` runs them sequentially in one logical unit of work. One row per delivery matches the operator question ("did we process this delivery?") without prematurely modeling per-handler retries that don't exist.

**What it unlocks now:**

- Operators can query failure rate, by event type, over time windows.
- The Sentry alert rule (section 4) gets a backstop: a daily check of `WHERE status='received' AND received_at < now() - interval '10 min'` would catch "the dispatcher is silently dead" — though that check itself is out of scope for this RFC (no scheduled query yet).
- Foundation for a future replay endpoint and for switching off `BackgroundTasks` in favour of a worker if we ever need to.

**What it does not unlock (deferred):**

- Automatic in-process replay of failed events.
- Payload body storage (would require a PII / retention policy — out of scope).
- An admin surface to browse / requeue events.

---

## Scope

**In scope:**
- Add `tenacity` dependency.
- Add `_request_with_retry` helper to `GitHubClient`; route `get_installation_token`, `list_repos`, `list_environments` through it.
- 401-triggered token cache eviction + single retry.
- Honour `Retry-After` / `x-ratelimit-reset` on 429 and rate-limited 403.
- New `webhook_events` table + Alembic migration.
- Webhook route: insert receipt row before scheduling dispatch (own transaction).
- `_dispatch_event`: update row with terminal status + error message after handlers complete.
- Tests covering: GitHub retry behaviour (success, transient 503 retried to success, 429 with `Retry-After`, terminal 401 after one cache-evict retry, exhausted retries surfacing the original `httpx.HTTPStatusError`); webhook event recording (received row inserted, success/failure/no-handler status updates, duplicate `delivery_id` no-op).
- New runbook: `docs/runbooks/webhook-redelivery.md` (referencing the `webhook_events` table for triage queries).
- README updates: `server/README.md` retry policy + webhook events table paragraph; cross-link the runbook.
- Sentry alert rule + Railway healthcheck path + Railway deploy notification (configured in dashboards, captured in this RFC + runbook for repeatability).

**Out of scope (deferred):**
- Distributed retry queue.
- Per-tenant rate-limit isolation (we share one App so this is already structurally fine).
- Replacing FastAPI `BackgroundTasks` with a real job runner — orthogonal concern.
- Webhook payload body storage and an admin UI / replay endpoint over `webhook_events` — defer until we have a real ops trigger.
- Scheduled "stuck delivery" check (rows in `status='received'` past a threshold) — easy to add later once the table exists.

## Schema Changes

New table `webhook_events`:

| Column          | Type           | Notes                                                                 |
| --------------- | -------------- | --------------------------------------------------------------------- |
| `id`            | `UUID PK`      | Generated server-side.                                                |
| `delivery_id`   | `TEXT NOT NULL`| From `X-GitHub-Delivery` header. **`UNIQUE`**.                        |
| `event_type`    | `TEXT NOT NULL`| From `X-GitHub-Event` header.                                         |
| `action`        | `TEXT NULL`    | From payload `action` field if present.                               |
| `tenant_id`     | `UUID NULL`    | Resolved post-dispatch when known; nullable because installation events arrive before tenant match. |
| `received_at`   | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Set on insert.                                          |
| `processed_at`  | `TIMESTAMPTZ NULL` | Set on dispatcher update.                                         |
| `status`        | `TEXT NOT NULL`| One of: `received`, `succeeded`, `failed`, `no_handler`.              |
| `error_message` | `TEXT NULL`    | First handler exception's `str(exc)`, truncated to 2 KB.              |
| `payload_bytes` | `INTEGER NOT NULL` | Body length in bytes. We do not store the body itself.            |

Indexes:
- `UNIQUE (delivery_id)` — natural dedup.
- `(received_at DESC)` — operator queries by recency.
- `(status, received_at DESC)` — failure-rate / stuck-delivery queries.

No FK on `tenant_id` for now — tenant resolution happens inside handlers and we don't want a write ordering constraint between webhook ingest and tenant creation. Validate semantically in code.

## Config Changes

- Add `tenacity = "^9.0.0"` (or current major) to `server/pyproject.toml`.
- No new env vars. The retry policy is constants in code — tunables can be promoted to settings later if we ever need to.

## Files Touched

- `server/app/services/github_client.py` — retry helper, token-refresh-on-401, route existing methods through helper.
- `server/pyproject.toml` + `server/poetry.lock` — add `tenacity`.
- `server/tests/services/test_github_client.py` (new or extend existing) — retry behaviour tests with `httpx` MockTransport.
- `server/database/versions/<new>_add_webhook_events.py` — Alembic migration for the new table.
- `server/app/models/webhook_event.py` (new) — SQLAlchemy model.
- `server/app/services/webhook_service.py` — helpers `record_received(...)` and `record_outcome(delivery_id, status, error)`. Each opens its own session so the receipt row survives handler rollback.
- `server/app/routes/webhooks.py` — insert receipt row before `background_tasks.add_task(...)`; pass `delivery_id` to the dispatcher.
- `server/tests/routes/test_webhooks.py` (extend) — receipt row + status-update assertions, duplicate `delivery_id` no-op.
- `docs/runbooks/webhook-redelivery.md` (new) — references `webhook_events` for triage queries.
- `server/README.md` — short paragraphs on retry policy and `webhook_events` + link to runbook.

## Observability

- Each retried attempt logs at `WARNING` with `event=github_retry`, `attempt=N`, `status=...`, `wait_s=...`. Exhausted retries log at `ERROR` and re-raise — Sentry picks up the exception via the existing logging integration.
- Token eviction logs at `INFO` with `event=installation_token_evicted`, `installation_id=...`.
- Webhook receipt logs at `INFO` with `event=webhook_received`, `delivery_id=...`, `event_type=...`, `action=...`. Outcome logs at `INFO` (`webhook_processed`) or `ERROR` (`webhook_failed`, with `error=...`).
- The `webhook_events` table is the structured equivalent — operators can answer "what's our handler failure rate?" via SQL without grepping logs.
- No new metrics. Sentry breadcrumbs + structured logs + the table are enough at this stage; we can add a counter later if retry pressure becomes a recurring topic.

## Risks and Mitigations

| Risk                                                                                  | Mitigation                                                                                                                       |
| ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Retry loop masks a real GitHub outage by silently extending request latency.          | Bounded total wall-clock (~20s per call); structured logs on every retry; Sentry sees exhaustion.                                |
| Token-evict-and-retry on 401 hides a genuinely revoked installation as transient.     | Only **one** retry post-eviction; second 401 surfaces normally and Sentry catches it.                                            |
| Sentry alert is noisy on a flaky GitHub day.                                          | Use the burst rule (>5 in 5min) plus first-occurrence rule; tune threshold if it's chatty for the first week.                    |
| Railway healthcheck restarts the container during a long-running install sync.        | `/health` is a lightweight DB-free endpoint; install sync runs in a `BackgroundTask` and doesn't block the event loop. Low risk. |
| `Retry-After` of 60s blocks an event-loop slot for too long.                          | Cap honoured wait at 30s per attempt; beyond that we fail and let the caller decide (webhook handler will surface to Sentry).    |
| `webhook_events` insert fails (DB blip) and we 500 a webhook GitHub will retry.       | Receipt insert is one row, no FK joins, near-zero failure surface. If it does fail we want GitHub to retry, so 500 is correct.   |
| `webhook_events` grows unbounded.                                                     | At current volumes (~hundreds of events/day) growth is negligible for years. Add a retention policy later if needed; not now.    |

---

## Implementation Plan

The work splits into three independent code phases (A, B+C, D) plus operator config (E). Phase A and Phase B can be done in parallel by separate PRs if useful, but the simplest path is sequential. Each step follows red/green TDD: failing test first, then the minimum implementation to turn it green, then refactor.

### Phase A — GitHub client retries

Goal: outbound calls in `GitHubClient` survive transient errors and rate limits without changing public method signatures.

**A1. Add `tenacity` dependency.**
- `cd server && poetry add tenacity@^9.0.0`
- Verify `poetry.lock` updates and `make lint-server` still passes (no usage yet, so just an import-availability check).

**A2. Failing tests for `_request_with_retry` (new file `server/tests/test_github_client.py`).**
Tests use the project's existing pattern: `patch("httpx.AsyncClient", return_value=mock_client)` (see `tests/test_clerk_service.py` for reference). Each test sets up a `Mock` whose `.get` / `.post` returns canned `httpx.Response` objects.
- `test_request_succeeds_first_try` — single 200, asserts one call made.
- `test_request_retries_on_503_then_succeeds` — 503, 200; asserts two calls.
- `test_request_retries_on_transport_error_then_succeeds` — raises `httpx.ConnectError` first, then 200.
- `test_request_does_not_retry_on_404` — 404 surfaces immediately as `httpx.HTTPStatusError`.
- `test_request_exhausts_retries_and_raises` — 503 four times, asserts last `HTTPStatusError` raised, asserts exactly four calls made.

**A3. Implement `_request_with_retry` helper in `server/app/services/github_client.py`.**
- Private async method on `GitHubClient`. Signature: `async def _request_with_retry(self, method: str, path: str, **kwargs) -> httpx.Response`.
- Use `tenacity.AsyncRetrying` with:
  - `stop=stop_after_attempt(4)`
  - `wait=wait_exponential_jitter(initial=1, max=8)` (the `jitter` variant gives full jitter)
  - `retry=retry_if_exception(_is_retryable)` where `_is_retryable` returns True for `httpx.TransportError`, `httpx.ReadTimeout`, and an `HTTPStatusError` whose `response.status_code` is in `{429, 502, 503, 504}`.
  - `reraise=True` so the original exception surfaces on exhaustion.
- Log `WARNING` with `event=github_retry`, `attempt`, `status`, `wait_s` from a `before_sleep` callback.
- Route `list_repos`, `list_environments`, and the token POST in `get_installation_token` through it. Public signatures stay unchanged.
- Run A2 tests → green.

**A4. Failing tests for `Retry-After` / `x-ratelimit-reset` honouring.**
- `test_request_honours_retry_after_on_429` — 429 response with `Retry-After: 2`, then 200. Assert that `tenacity`'s wait was ≥2s. (Use `unittest.mock.patch` on `asyncio.sleep` to capture the awaited duration without actually sleeping.)
- `test_request_caps_retry_after_at_30s` — 429 with `Retry-After: 120`, asserts capped at 30s.
- `test_request_uses_x_ratelimit_reset_when_no_retry_after` — 403 with `x-ratelimit-remaining: 0` and `x-ratelimit-reset: <epoch+5s>`, asserts wait ≈5s.

**A5. Implement server-supplied wait.**
- Replace the bare `wait_exponential_jitter` with a custom `wait` callable that:
  1. Inspects the last attempt's exception. If it's a 429/403-rate-limit `HTTPStatusError`, compute the server-supplied delay from `Retry-After` (seconds or HTTP-date) or from `x-ratelimit-reset` (epoch).
  2. Cap the result at 30s.
  3. Otherwise fall back to exponential jitter.
- Run A4 tests → green.

**A6. Failing tests for token-refresh-on-401.**
- `test_401_evicts_token_cache_and_retries_once` — first call returns 401, second succeeds. Assert cache entry for the `installation_id` was evicted and a fresh `POST /access_tokens` was issued. Assert public method returns successfully.
- `test_terminal_401_after_eviction_surfaces` — both attempts return 401. Assert exactly two attempts (no further loop) and `HTTPStatusError` is raised.

**A7. Implement 401 handling.**
- Wrap the per-call path inside `list_repos` / `list_environments` (the two methods that carry an installation token) so that a single 401 triggers `_token_cache.pop(installation_id, None)` and one re-issue. This logic lives outside the `tenacity` loop — it is a one-shot, not part of exponential backoff. The simplest shape: a small `_with_token_refresh(installation_id, fn)` helper that runs `fn()`, catches `HTTPStatusError(401)`, evicts, and re-runs once.
- Run A6 tests → green.

**A8. Verify and tidy.**
- `make lint-server` → clean.
- `make test` → all green (existing tests must still pass — `test_installation_service.py:59` patches `GitHubClient` so should be unaffected; sanity check anyway).
- One smoke test in dev: trigger an installation flow against a test GitHub App, confirm logs show no retries on the happy path.

### Phase B — `webhook_events` schema and model

Goal: the table exists and the model is queryable. No write-path changes yet.

**B1. Add SQLAlchemy model `server/app/models/webhook_event.py`.**
- Mirror existing model style (`models/pull_request.py` is a representative example).
- Columns exactly as the Schema Changes table in this RFC.
- `delivery_id` has `unique=True`; the index pair on `(received_at)` and `(status, received_at)` declared via `__table_args__`.

**B2. Generate Alembic migration.**
- `cd server && poetry run alembic revision --autogenerate -m "add webhook_events"`
- Inspect the generated file in `server/database/versions/`. Confirm: only the new table is created, indexes match, defaults render correctly (`server_default=text("now()")` for `received_at`).
- Hand-edit if autogenerate misses the indexes (it sometimes does for non-FK indexes).

**B3. Apply migration locally.**
- `make migrate` against the dev DB. Confirm `\d webhook_events` shows expected columns + indexes.

**B4. Migration round-trip test.**
- A minimal integration test (or extend an existing migration smoke test if one exists) that inserts a row via the model and reads it back, asserting all columns persist correctly. If the project has no such pattern, skip — the route-level tests in Phase C will exercise the model.

### Phase C — Wire the receipt + outcome writes

Depends on B.

**C1. Failing tests for `record_received` (extend `tests/test_webhook_service.py`).**
- `test_record_received_inserts_row` — call helper, query DB, assert row exists with `status='received'`, `received_at` set, `processed_at` null, payload_bytes correct.
- `test_record_received_duplicate_delivery_id_is_noop` — call twice with same `delivery_id`, assert exactly one row.
- These tests use the existing async session fixture from `conftest.py`.

**C2. Implement `record_received` in `server/app/services/webhook_service.py`.**
- Signature: `async def record_received(delivery_id: str, event_type: str, action: str | None, payload_bytes: int) -> None`.
- Opens its **own** `async_session()`, performs `insert(...).on_conflict_do_nothing(index_elements=["delivery_id"])`, commits, closes.
- The own-session requirement is non-negotiable: the dispatcher's session can roll back, and the receipt row must survive that rollback.

**C3. Failing tests for `record_outcome`.**
- `test_record_outcome_marks_succeeded` — pre-insert a `received` row; call `record_outcome(delivery_id, "succeeded", None)`; assert row updated, `processed_at` set, `error_message` null.
- `test_record_outcome_marks_failed_with_error` — assert `status='failed'`, `error_message` populated.
- `test_record_outcome_truncates_long_error` — pass an error string >2KB, assert stored value is exactly 2048 chars.
- `test_record_outcome_unknown_delivery_id_is_noop` — call against a non-existent `delivery_id`, assert no exception (defensive — dispatcher races shouldn't crash).

**C4. Implement `record_outcome`.**
- Signature: `async def record_outcome(delivery_id: str, status: str, error: str | None) -> None`.
- Own session (same reasoning as C2). `update(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id).values(...)`. No-op when no row matches.
- Truncate `error` to 2048 chars before storing.

**C5. Failing end-to-end tests in `tests/test_webhooks.py`.**
- `test_webhook_records_received_then_succeeded` — POST a valid `pull_request` event, assert webhook_events row exists with terminal status `succeeded`.
- `test_webhook_records_failed_when_handler_raises` — register a handler that raises; assert row ends as `failed` with non-empty `error_message`. Use the existing `EVENT_HANDLERS` registry pattern from `test_webhook_service.py:38-50`.
- `test_webhook_records_no_handler_for_unknown_event_type` — POST with an unregistered `X-GitHub-Event`, assert row exists with status `no_handler`.
- `test_rejected_webhook_does_not_create_row` — POST with bad HMAC, assert no row was inserted.

**C6. Update `server/app/routes/webhooks.py`.**
- After all rejection checks pass, before `background_tasks.add_task(...)`:
  ```
  delivery_id = request.headers.get("X-GitHub-Delivery", "")
  if not delivery_id:
      return Response(status_code=400)  # GitHub always sends this; missing = malformed
  await record_received(delivery_id, event_type, payload.get("action"), len(body))
  background_tasks.add_task(_dispatch_event, event_type, payload, delivery_id)
  ```
- Bubble the `delivery_id` through the dispatcher signature.

**C7. Update `_dispatch_event` in the same file.**
- Track per-handler outcomes locally. After all handlers run:
  - If no handlers were registered: `await record_outcome(delivery_id, "no_handler", None)`.
  - If any handler raised: `await record_outcome(delivery_id, "failed", first_error_message)`.
  - Otherwise: `await record_outcome(delivery_id, "succeeded", None)`.
- Preserve current behaviour: handlers continue running even if an earlier one fails (the loop already handles this).

**C8. Verify.**
- `make test` → all green, including pre-existing `test_webhooks.py` cases.
- `make lint-server` → clean.
- Smoke test in dev: send a real webhook from the GitHub App or curl a signed payload, query `SELECT * FROM webhook_events ORDER BY received_at DESC LIMIT 5;` and confirm the row + transition.

### Phase D — Documentation

**D1. Write `docs/runbooks/webhook-redelivery.md`.**
Sections:
- **When to use**: data quality `attribution_coverage` drop, customer-reported missing deployment, Sentry alert from `app.routes.webhooks`.
- **Step 1: confirm what arrived.** SQL snippet:
  ```sql
  SELECT delivery_id, event_type, action, status, error_message, received_at
  FROM webhook_events
  WHERE event_type = 'deployment_status'
    AND received_at > now() - interval '1 day'
  ORDER BY received_at DESC;
  ```
- **Step 2: cross-check with GitHub.** GitHub App settings → Advanced → Recent Deliveries; how to filter by event type and find the `X-GitHub-Delivery` ID matching (or missing from) our table.
- **Step 3: redeliver.** Click Redeliver on the GitHub side. Note that the redelivery gets a fresh `delivery_id` so it appears as a new row in `webhook_events` — that is correct.
- **When NOT to redeliver.** If `webhook_events.status='succeeded'` for that delivery, processing is complete; redelivery is a no-op for `deployment_status` (idempotent on `(tenant_id, deployment_id)`) and `pull_request` (UPSERT) — but it adds a row and creates noise.

**D2. Update `server/README.md`.**
- Under "Webhook events" table or as a sibling section: one paragraph naming `webhook_events`, the four statuses, link to the runbook.
- New "GitHub API retries" section: one paragraph stating the policy (4 attempts, exponential + jitter, server-supplied delays honoured up to 30s, automatic token refresh on 401) and the relevant file (`app/services/github_client.py`).

### Phase E — Operator configuration (no code; requires the human)

Captured here so the work isn't "done" until these are in place.

**E1. Sentry alert rule.**
- In Sentry → Alerts → Create Alert → Issue Alert.
- Conditions: "An issue is first seen" AND `logger:app.routes.webhooks`.
- A second rule: "The issue is seen more than 5 times in 5 minutes" with the same logger filter.
- Actions: send to the chosen Slack channel (#alerts or #ingest — TBD).

**E2. Railway healthcheck.**
- Web service settings → Health Check Path: `/health`.
- Leave defaults for timeout/interval unless they are unset.

**E3. Railway deploy notifications.**
- Project settings → Notifications → enable Slack integration on deploy events for the `server` service.

**E4. Sanity-check production env.**
- Confirm `SENTRY_DSN` is set on the Railway production environment (it should already be — verify, do not assume). Re-deploy if it was missing.

### Definition of Done

- All Phase A–C tests green; coverage for `github_client.py` and the new `webhook_service.py` helpers ≥ existing project baseline.
- `make lint-server` clean; `make test` clean.
- Migration applies cleanly on a fresh DB and on the existing dev DB.
- Manual smoke: trigger a GitHub installation against a test App, confirm `webhook_events` shows the lifecycle `received → succeeded` and no retries fired on the happy path.
- Runbook published at `docs/runbooks/webhook-redelivery.md` and linked from `server/README.md`.
- Sentry alert rule live and tested by deliberately raising in a test handler in dev (or using Sentry's "send test event" feature).
- Railway healthcheck path saved; visible as healthy in the Railway dashboard.

### Suggested PR Carving

One PR is fine if the diff stays small. If it grows, split:
1. **PR 1: GitHub client retries** — Phase A only. Self-contained, reviewable in isolation.
2. **PR 2: Webhook events table + writes + docs** — Phases B, C, D.
3. **(Out of band): Phase E configuration** — non-code, captured in the runbook.
