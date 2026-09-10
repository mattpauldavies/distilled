# ADR 008: Structured JSON Logging on stdout

**Date:** 2026-09-10
**Status:** Accepted
**Supersedes:** n/a

## Context

Railway classifies anything a container writes to **stderr** as `level.error` and
colours it red in the log explorer. Its documentation is explicit that it "does not
take into account the INFO portion of the log message as there is no true standard
for that" — the stream is the signal.

`configure_logging` attached a bare `logging.StreamHandler()`, which defaults to
`sys.stderr`. Every application log line in production was therefore reported as an
error, including ordinary records such as `attributed 1 PRs to deployment=…` and
`webhook_received delivery_id=… event_type=deployment_status`.

Uvicorn compounded the confusion. It installs its own handlers at boot, before our
`lifespan` hook runs, with `propagate = False` — so clearing the root logger's
handlers never reached them. `uvicorn.access` writes to stdout while `uvicorn.error`
writes to stderr, which is why request lines looked healthy while application lines
looked like failures.

The cost was not cosmetic. With every line red, there was no way to tell a genuine
failure from routine chatter, and "the cron and invitation services are failing"
could not be confirmed or ruled out from the logs. Sentry captures unhandled
exceptions and showed none, but rate-limit rejections return a `429` rather than
raising, so they are invisible to Sentry too — exactly the class of failure the logs
should have surfaced and could not.

## Decision

Write all logs to **stdout**, and in production format each record as a single JSON
line using Railway's field contract: `message` for the log text, `level` for the
severity, and any further keys as filterable attributes.

Severity comes from the record, so `WARNING` maps to Railway's `warn` and only
`ERROR`/`CRITICAL` map to `error`. Development keeps the existing human-readable
format on the console and in `logs/dev.log`.

Uvicorn's `uvicorn`, `uvicorn.error` and `uvicorn.access` loggers have their handlers
cleared and propagation re-enabled, so the whole process emits one consistent stream.

`httpx` and `httpcore` drop to `WARNING`. They log one `INFO` line per outbound
request, so a single Clerk user lookup or GitHub call produced a log line we never
asked for — the highest-volume "error" in production was a successful HTTP 200.

## Consequences

**Positive:**

- Severity in the log explorer reflects what the code actually said. `@level:error`
  now returns real failures and nothing else.
- Attributes are filterable: `@logger:app.services.invitation_service` follows one
  module across a deploy without grepping.
- One stream, one format, for application and server logs alike.
- Substantially less log volume, and what remains is signal.

**Negative:**

- Production logs are no longer pleasant to read raw. Tailing a deploy shell now
  means piping through `jq`. This is the accepted cost of machine-readable severity;
  development is unchanged, and Railway's explorer renders the parsed fields.
- The JSON field names are coupled to Railway's contract. Another host would want a
  different mapping, though `message`/`level` is close to universal.

## Alternatives considered

**Everything to stdout as plain text.** One line changed, but then every record is
`info` and genuine errors lose their severity — the same blindness, inverted.

**Split by level: INFO/DEBUG to stdout, WARNING+ to stderr.** No format change, and
errors colour correctly. Rejected because `WARNING` would still be reported as
`error` — stderr is stderr — and we would be encoding severity in the stream rather
than stating it.

**A logging library (`structlog`, `python-json-logger`).** A dependency and a
migration of every call site, to replace roughly thirty lines of formatter. Revisit
if we want request-scoped context binding.
