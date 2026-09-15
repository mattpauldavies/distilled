# Security Posture

**Status:** Shipped, with an open backlog
**Consolidates:** RFC 015 (security and architecture hardening), RFC 017 (server security audit)

## Summary

Two full security reviews have been run against the server: one before any production
exposure, one after the move to multi-tenant SaaS auth. This records the controls that came
out of them, what remains open, and the reasoning behind the choices — so a future review
starts from the current position rather than rediscovering it.

Individual findings are not reproduced in detail. The fixes are in the code and its tests;
what is worth keeping is the shape of the defence and the trade-offs taken.

## Controls in place

**Authentication.** Every user-facing route requires a Clerk JWT, verified against JWKS with
signature, expiry, audience, and issuer all checked. Internal cron routes live in their own
router with the shared-secret check applied **at router level**, not per route — see the
decision below. Health and the webhook receiver are the only unauthenticated endpoints.

**Workspace isolation.** Every domain table carries `tenant_id`; the active workspace is
resolved per request with membership verified server-side; list endpoints validate repo
ownership through `get_verified_repo`. Cross-table joins in detail endpoints carry their own
`tenant_id` filter rather than relying on the joined row's integrity.

**Webhook integrity.** HMAC-SHA256 with `hmac.compare_digest`, an explicit rejection when
the secret is empty, a `Content-Length` pre-check before the body is read, content-type
validation, and parsing from the already-read bytes rather than a second `request.json()`.

**Transport and headers.** Explicit CORS origins with scoped methods and headers, security
headers including HSTS and CSP, and TLS enforced on the database connection in production.
OpenAPI docs are disabled in production.

**Secrets.** No default database credentials — the app refuses to start without explicit
configuration. Startup validation fails hard in production when any required secret is
empty. Seed and reset scripts refuse to run against production.

**Rate limiting.** Applied per route with limits matched to each endpoint's real traffic
shape. See the keying caveat in [006 Observability](006-observability.md) — limits are only
per-caller when `FORWARDED_ALLOW_IPS` is set, because behind Railway's edge proxy
`request.client.host` is otherwise the proxy.

**Input handling.** SQLAlchemy ORM with parameterised filters throughout; URLs arriving from
GitHub payloads are validated before storage; pagination is bounded at 100 rows; the
environment update schema accepts one boolean, so mass assignment is impossible; no
`dangerouslySetInnerHTML` or `eval` in the frontend.

**Error surfaces.** Services raise framework-free errors translated at the boundary; JWT
failures return a generic message to the client and log details server-side; error stack
traces go to Sentry, not the browser console.

**Installation claims.** Binding a GitHub installation to a workspace requires proof the
caller controls it — the single most serious finding either review produced. The design is
in [004 Accounts and Workspaces](004-accounts-and-workspaces.md).

## Decisions

**Internal endpoints get their own router.** When cron-secret routes shared a router with
the user-facing metrics API, auth had to be declared per route, and one forgotten
declaration would have been an unauthenticated endpoint. Router-level auth makes that
mistake unavailable. URL paths were kept stable because the Railway cron service and the
fan-out script pin them.

**The cron secret spans workspaces, and that is documented rather than fixed.** Recompute
takes a `(tenant_id, repo_id)` pair from the caller and validates that the pair exists. A
leaked cron secret is a privilege boundary breach by definition; per-tenant scheduler
authentication would be a real improvement but is not what stands between us and the current
threat model. The rate limit bounds the damage to roughly one fan-out per hour.

**The webhook receipt row is written in its own transaction.** It must survive the handler's
rollback, otherwise a failed delivery leaves no evidence it ever arrived.

**A 500 on a failed webhook receipt insert is correct.** If we cannot record a delivery, we
want GitHub to retry it.

**Defence in depth over a single check.** Attribution and metric queries filter on
`tenant_id` even where `repo_id` alone would be unique today. The cost is one clause; the
benefit is that a future data-integrity bug does not become a cross-workspace leak.

## Open backlog

These were identified, judged non-blocking, and deliberately not done:

- **Async webhook processing with retry and a dead-letter queue.** `BackgroundTasks` is
  in-process, so a crash mid-dispatch loses the event. Needs its own proposal — it is an
  architecture change, not a hardening step.
- **Shared multi-worker GitHub token cache.** The installation token cache is per-process, so
  each worker mints its own token and multiplies GitHub API calls. Needs Redis or a database
  table.
- **JWKS cache refresh on `kid` miss.** If Clerk rotates signing keys, tokens signed with the
  new key are rejected until the one-hour TTL expires.
- **Per-tenant authentication for scheduled work**, replacing the shared cron secret.
- **Dependency vulnerability scanning** as a CI step.
- **Encryption at rest for stored GitHub tokens.**

## History

- **RFC 015** (pre-production) found three critical issues — no authentication on any
  endpoint, wildcard CORS, and a webhook signature bypass when the secret was empty — plus a
  set of high and medium findings. It introduced a static API key as a stopgap and set out a
  phased remediation.
- **RFC 016** replaced that static API key with Clerk JWT auth — see
  [004 Accounts and Workspaces](004-accounts-and-workspaces.md).
- **RFC 017** audited the server again after the auth change: 21 findings across 50+ source
  files, no SQL injection, with the significant issues clustered around JWT validation gaps,
  tenant isolation on joins, a TOCTOU race in user provisioning, and missing production
  hardening. All critical and high findings are resolved.
- **September 2026 security review** found and fixed the installation-claim authorisation
  hole (ADR 010).
