# ADR 003 — Transaction Boundaries: Entry Points Commit, Services Flush

**Date:** 2026-09-08
**Status:** Accepted

## Context

Commit calls were scattered across layers with no stated owner: some routes committed,
the webhook dispatcher committed per handler, and `user_service` committed mid-request.
With no convention, every new feature guesses, and a service that commits early makes it
impossible for its caller to roll the whole request back.

## Decision

**Entry points own the transaction; services `flush()` only.**

Entry points are the places a request or job enters the system:

- HTTP route handlers (e.g. `routes/internal.py` commits after `recompute_repo_and_log`)
- The webhook dispatcher (`routes/webhooks.py::_dispatch_event` commits per handler and
  rolls back on failure)
- Scripts (`scripts/seed_demo.py` commits once at the end)

Services may `flush()` to obtain generated IDs or surface constraint errors early, but must
not `commit()` — the caller decides when the unit of work is complete.

## Exception

`user_service.get_or_create_user` (called from the `require_auth` dependency)
commits its own user/tenant creation. This is deliberate: user provisioning must persist
independently of whether the request that triggered it later fails, and the commit is
integral to the IntegrityError handling for concurrent first logins. Auth-time provisioning
is treated as its own entry point.

## Consequences

- A failing handler can roll back everything it did — no partially-applied webhook events.
- Reviewers can reject a `commit()` inside `app/services/` on sight (except the documented
  auth exception).
