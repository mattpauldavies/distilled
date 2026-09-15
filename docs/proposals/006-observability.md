# Observability and Analytics

**Status:** Shipped
**Consolidates:** PRD 002 (local logging), RFC 002, RFC 025 (production log severity and rate-limit keying), ADR 007 (PostHog reverse proxy), ADR 008 (structured production logging)

## Summary

Logs that tell the truth about severity, errors that reach Sentry, and product analytics
that are not silently half-missing. The common thread is the same one the product sells:
data you can act on without second-guessing whether it is complete.

## Logging

### Development

Human-readable console output plus a file at `server/logs/dev.log`, truncated on start, so a
crash can be inspected after the fact. Enabled only when `ENVIRONMENT=development`; the
setting defaults to `production`, so a deployment is safe without explicit configuration.
`logs/` is gitignored. Stdlib logging throughout — no new dependency, and it works with the
`logging.getLogger(__name__)` calls already spread across the codebase.

### Production

All logs go to **stdout**, formatted as one JSON line per record using Railway's field
contract: `message` for the text, `level` for the severity, everything else as a filterable
attribute.

The stream is the point. Railway classifies anything written to **stderr** as `level.error`
and colours it red, and its documentation is explicit that it does not read the INFO portion
of the message because there is no standard for it. A bare `logging.StreamHandler()`
defaults to stderr, so every application log line in production was being reported as an
error — including `attributed 1 PRs to deployment=…` and `webhook_received …`.

That was not cosmetic. With every line red, a genuine failure was indistinguishable from
routine chatter, and "the cron and invitation services are failing" could be neither
confirmed nor ruled out. Sentry showed no unhandled exceptions, but rate-limit rejections
return a 429 rather than raising, so they are invisible to Sentry too — exactly the class of
failure the logs should have surfaced and could not.

Two supporting changes make the stream consistent:

- **Uvicorn's loggers are reparented onto root.** Uvicorn installs its own handlers at boot,
  before our lifespan hook runs, with `propagate = False` — so clearing the root logger never
  reached them. `uvicorn.access` writes to stdout while `uvicorn.error` writes to stderr,
  which is why request lines looked healthy while application lines looked like failures.
- **`httpx` and `httpcore` drop to WARNING.** They log one INFO line per outbound request, so
  a single Clerk user lookup or GitHub call produced a log line nobody asked for. The
  highest-volume "error" in production was a successful HTTP 200.

Severity now comes from the record: WARNING maps to Railway's `warn`, and only
ERROR/CRITICAL map to `error`.

### Errors

Sentry is initialised at module scope in both tiers. On the client that matters — it used to
run inside a `useEffect` in the signed-in component, so errors during sign-in and in the
top-level error boundary were never reported.

Webhook handler failures are captured through the logging integration. Alerting is a Sentry
rule rather than code: first occurrence on `logger:app.routes.webhooks`, plus a burst rule
of more than five in five minutes, routed to Slack.

## Rate-limit keying

Rate limits are keyed on `request.client.host`. Uvicorn only rewrites that from
`X-Forwarded-For` when the peer is in `forwarded_allow_ips`, which defaults to `127.0.0.1`.
Railway's edge proxy is not `127.0.0.1`, so without configuration `request.client.host` is a
constant proxy address and the entire user base shares one bucket.

`FORWARDED_ALLOW_IPS` is therefore **required deployment configuration**, documented in
`.env.example` and the server README. Setting it to `*` is only safe when the container is
reachable exclusively through a trusted proxy — which is the case on Railway, where the
container port is not publicly exposed.

A custom `key_func` reading `X-Forwarded-For` directly was rejected: it duplicates logic
uvicorn already implements correctly, and hand-rolled header parsing is precisely where
IP-spoofing bypasses come from.

## Product analytics

PostHog events from both the client and the marketing website are sent to
`https://d.distilledmetrics.com` — a CNAME onto PostHog's managed reverse proxy — rather
than to `eu.i.posthog.com`.

PostHog's own domains appear on the default block lists shipped with uBlock Origin, AdGuard,
Brave, and Safari and Firefox tracking protection, so a share of requests never left the
browser. The loss was silent: `posthog-js` reports no error when a request is blocked at the
network layer, so the numbers looked plausible while being biased by whichever browsers and
blockers our users happen to run. Correcting for that statistically is unworkable, because
the bias depends on the very data that is missing.

Because `api_host` is no longer PostHog's own domain, `ui_host` is set to
`https://eu.posthog.com` so SDK-generated links resolve to the PostHog app. Both are
overridable by environment variable, so falling back to PostHog directly is a redeploy
rather than a code change.

Nothing changed about what is collected, who processes it, or where it is stored — the proxy
is PostHog's own managed infrastructure and data still lands in the EU region. See
[analytics.md](../analytics.md) for what is collected.

## Accepted consequences

- **Production logs are no longer pleasant to read raw.** Tailing a deploy means piping
  through `jq`. That is the price of machine-readable severity; development is unchanged and
  Railway's explorer renders the parsed fields.
- **The JSON field names are coupled to Railway's contract.** Another host would want a
  different mapping, though `message`/`level` is close to universal.
- **A few boot lines still land on stderr.** `configure_logging` runs inside the lifespan
  hook, so uvicorn's "Started server process" lines precede it. Capturing those would mean
  shipping a `--log-config` file and giving up the settings object — not worth it.
- **The analytics proxy defeats tracker blocking**, which some people deliberately enable.
  That is defensible only because the analytics are genuinely anonymous and cookieless —
  nothing is stored on the device, no person profile is created, `identify()` is never
  called — and because the privacy policy names PostHog. It would not be defensible if the
  privacy posture changed.
- **A new DNS dependency.** If `d.distilledmetrics.com` stops resolving, analytics stops —
  silently, in the same way blocked requests did.

## Alternatives rejected

**Everything to stdout as plain text.** One line changed, but then every record is `info` and
genuine errors lose their severity — the same blindness, inverted.

**Split by level: INFO/DEBUG to stdout, WARNING+ to stderr.** No format change and errors
colour correctly, but WARNING would still be reported as `error`, because stderr is stderr.
That encodes severity in the stream rather than stating it.

**A logging library (`structlog`, `python-json-logger`).** A dependency and a migration of
every call site, to replace roughly thirty lines of formatter. Worth revisiting if we want
request-scoped context binding.

**Self-hosting the analytics proxy.** More control, but it adds an availability-critical
service to operate, patch, and monitor for no benefit over PostHog's managed offering.

## History

- **PRD 002 / RFC 002** added development file logging.
- **RFC 020** added the Sentry alert rules and the webhook redelivery runbook — see
  [001 Deployment Ingest](001-deployment-ingest.md).
- **ADR 007** moved analytics behind the first-party proxy.
- **RFC 025 / ADR 008** moved logs to stdout with JSON in production, reparented uvicorn's
  loggers, quietened `httpx`, and corrected the rate-limit keying and the recompute limit.
