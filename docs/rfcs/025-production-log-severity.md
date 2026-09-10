# RFC 025: Production Log Severity and Rate-Limit Keying

---

## Summary

Every application log line in production is reported as an **error**, including ordinary
`INFO` records such as `attributed 1 PRs to deployment=…` and `webhook_received …`. The
cause is not the log records — it is where they are written. `configure_logging` attaches a
bare `logging.StreamHandler()`, which defaults to **stderr**, and Railway classifies
anything a container writes to stderr as `level.error` regardless of content.

The consequence is not cosmetic. Genuine failures are indistinguishable from routine
chatter, so "the cron and invitation services are failing" is currently unfalsifiable from
the logs alone.

This RFC routes application logs to **stdout**, formats them as single-line JSON in
production so Railway reads the real severity from a `level` field, and silences
third-party per-request `INFO` noise.

It also corrects a second, genuine defect uncovered while investigating: rate limits are
keyed on `request.client.host`, which behind Railway's edge proxy is the **proxy's**
address rather than the caller's. Every caller therefore shares a single bucket, and the
hourly metrics fan-out throttles itself.

---

## Background

### Why the logs are red

`server/app/logging.py` builds the root handler like this:

```python
console = logging.StreamHandler()
```

`logging.StreamHandler()` with no argument writes to `sys.stderr`. Confirmed by inspecting
the configured handler directly:

```
root handler: StreamHandler -> STDERR
httpx effective level: INFO
```

Railway's documented behaviour is that "logs emitted to stderr will be converted to
`level.error` and coloured red", and that it "does not take into account the INFO portion
of the log message as there is no true standard for that". This is a well-known trap for
Python and uvicorn deployments on the platform.

That explains the exact shape of the reported symptom — the `severity: "error"` and
`attributes.level: "error"` fields are Railway's, applied by stream, not ours:

```json
{
  "message": "… INFO app.services.attribution_service: attributed 1 PRs to deployment=…",
  "severity": "error",
  "attributes": { "level": "error" }
}
```

### Why only *some* lines are red

Uvicorn installs its own logging configuration at boot, before our `lifespan` hook runs.
Its `uvicorn.access` logger writes to **stdout** and `uvicorn.error` to **stderr**, and
both have `propagate = False`, so `configure_logging` — which only clears the *root*
logger's handlers — never touches them. Request access lines therefore look healthy while
every application log looks like a failure.

### The `httpx` noise

`httpx` logs one `INFO` line per outbound request. Every Clerk user lookup and every GitHub
API call emits one, which is where the reported `HTTP Request: GET
https://api.clerk.com/v1/users/… "HTTP/1.1 200 OK"` line comes from. Combined with the
stderr routing, the highest-volume "error" in the logs is a successful HTTP 200.

### Are the services actually failing?

Sentry — which captures real exceptions via the `unhandled_exception_handler` — holds
**one** issue across the last 90 days, already resolved (the installation-token 401 fixed
in `7b9b987`). No unhandled exception is reaching production.

Rate limiting, however, does not raise. `SlowAPIMiddleware` returns a `429` response
rather than raising `RateLimitExceeded`, so throttling is invisible to Sentry *and*,
until this RFC lands, indistinguishable from routine logs. Two throttling defects exist:

**1. Rate limits are keyed on the proxy's IP.** The limiter is built with
`key_func=get_remote_address` (`server/app/rate_limit.py`), which returns
`request.client.host` — the peer socket address. Uvicorn only rewrites that from
`X-Forwarded-For` when the peer is in `forwarded_allow_ips`, which defaults to
`127.0.0.1`:

```python
if forwarded_allow_ips is None:
    self.forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
```

Railway's edge proxy is not `127.0.0.1`, so `request.client.host` is a constant proxy
address for every public request. The `200/minute` default limit is therefore shared by the
**entire user base**, including `POST /invitations/redeem`. RFC 015 specified "conservative
per-IP defaults" and RFC 017 implemented the decorators; neither accounted for the proxy
hop, so the per-IP intent does not hold in production.

**2. The hourly fan-out throttles itself.** `POST /metrics/recompute` carries
`@limiter.limit("10/minute")`, but `scripts/run_hourly_recompute.py` calls it **once per
repository** with `CONCURRENCY=3`. Past ten repositories in a rolling minute, the remainder
receive `429`. `recompute_one` does not retry a `429` (it retries only `>= 500`), returns
`False`, and `main()` still exits `0` after printing `failed=N` — so the run is recorded as
a success while metrics silently go stale.

---

## Decision

### 1. Application logs go to stdout

Pass `sys.stdout` explicitly to the console handler. Severity then comes from the record,
not from the stream.

### 2. Production logs are single-line JSON

Railway parses a JSON log line and uses `message` for the text and `level` for the
severity, exposing every other key as a filterable attribute. Production emits JSON;
development keeps the existing human-readable `LOG_FORMAT` for the console and the
`dev.log` file.

`WARNING` maps to Railway's `warn`; `CRITICAL` maps to `error`, which is the most severe
level Railway offers.

### 3. Uvicorn's loggers are routed through root

Clear the handlers on `uvicorn`, `uvicorn.error` and `uvicorn.access` and re-enable
propagation, so the whole process emits one consistent stream on stdout. Without this,
uvicorn's own startup and error lines stay on stderr and stay red.

`configure_logging` runs inside `lifespan`, so the few lines uvicorn emits before that
("Started server process", "Waiting for application startup") still land on stderr as plain
text. Capturing those would mean shipping a `--log-config` file and giving up the settings
object; not worth it for a handful of boot lines.

### 4. Third-party per-request logging drops to WARNING

`httpx` and `httpcore` log at `WARNING` and above. Our own request-level logging (
`webhook_received`, attribution counts) is unaffected — that is signal we control and want.

### 5. The metrics fan-out limit is expressed per hour

`POST /metrics/recompute` moves from `10/minute` to `1000/hour`. The endpoint's legitimate
traffic shape is one burst of *N* calls once per hour, where *N* is the repository count; a
per-minute cap cannot express that without either throttling the burst or being
meaningless. `1000/hour` accommodates a fan-out of up to 1,000 repositories while still
bounding a leaked cron secret to roughly one fan-out's worth of work per hour.

`/metrics/recompute-targets` keeps `10/minute` — it is called once per run.

### 6. `FORWARDED_ALLOW_IPS` is documented as required deployment configuration

Uvicorn reads this variable natively, so no code change is needed. Setting it to `*` on
Railway makes `request.client.host` the real client IP and restores per-IP limiting. It is
added to `.env.example` and the server README with the caveat that it is only safe when the
container is reachable *exclusively* through a trusted proxy — which is the case on
Railway, where the container port is not publicly exposed.

---

## Alternatives considered

**Send everything to stdout as plain text.** Simplest possible change, but then *every*
line is `info` and genuine errors lose their severity — the same blindness, inverted.

**Split by level: INFO/DEBUG to stdout, WARNING+ to stderr.** No format change and Railway
colours errors correctly, but `WARNING` is reported as `error` because stderr is stderr.
Rejected in favour of exact severity.

**Exempt the internal cron routers from rate limiting entirely.** Defensible — the shared
secret is the real privilege boundary — but it discards a defence-in-depth layer that RFC
017 deliberately added. A limit matched to the actual traffic shape keeps the layer without
breaking the fan-out.

**A custom `key_func` that reads `X-Forwarded-For` directly.** Duplicates logic uvicorn
already implements correctly, and hand-rolled header parsing is exactly where IP-spoofing
bypasses come from. Rejected.

---

## Implementation Plan

### Task 1: Log records carry their own severity — RED

- [x] **Step 1:** In `server/tests/test_logging.py`, assert the console handler's stream is
      `sys.stdout`, in both `development` and `production`.
- [x] **Step 2:** Assert that production formats records as JSON carrying `message`,
      `level`, `logger` and `timestamp`, and that `INFO` maps to `"info"`, `WARNING` to
      `"warn"`, `ERROR`/`CRITICAL` to `"error"`.
- [x] **Step 3:** Assert an exception record includes a rendered `exception` field.
- [x] **Step 4:** Assert development keeps the plain-text `LOG_FORMAT`.
- [x] **Step 5:** Assert `httpx` and `httpcore` sit at `WARNING`.
- [x] **Step 6:** Assert `uvicorn`, `uvicorn.error` and `uvicorn.access` have no handlers of
      their own and propagate to root.
- [x] **Step 7:** Run the suite; confirm the new tests fail for the stated reasons.

### Task 2: Implement the logging change — GREEN

- [x] **Step 1:** Add a `JsonFormatter` to `server/app/logging.py` emitting the Railway
      field contract, with a `logging.LogRecord` level → Railway level map.
- [x] **Step 2:** Pass `sys.stdout` to the console `StreamHandler`; select the formatter by
      environment.
- [x] **Step 3:** Keep the `dev.log` file handler on the plain-text format.
- [x] **Step 4:** Quieten `httpx`/`httpcore`; reparent the uvicorn loggers onto root.
- [x] **Step 5:** Run the suite; all green.

### Task 3: Stop the fan-out throttling itself

- [x] **Step 1:** Add a test asserting an eleventh `POST /metrics/recompute` within a minute
      is not rejected.
- [x] **Step 2:** Change the decorator to `1000/hour` with a comment deriving the number.
- [x] **Step 3:** Run the suite; all green.

### Task 4: Documentation

- [x] **Step 1:** `FORWARDED_ALLOW_IPS` in `server/.env.example` with the safety caveat.
- [x] **Step 2:** A logging section in `server/README.md` covering the JSON contract, how to
      filter by attribute in Railway, and the deployment variable.
- [x] **Step 3:** ADR 008 recording the stdout/JSON decision and the proxy-header trade-off.
- [x] **Step 4:** Note the rate-limit keying correction against RFC 015/017's per-IP intent.

### Task 5: Verification

- [x] **Step 1:** `make test-server` green.
- [x] **Step 2:** `ruff` and `mypy` clean.
- [x] **Step 3:** Render a sample production log line and confirm it parses as JSON with the
      expected `level`.
