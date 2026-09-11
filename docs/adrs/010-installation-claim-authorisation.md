# ADR 010: Installation claims require proof the caller controls the installation

## Status

Accepted (security review, September 2026)

## Context

The GitHub setup callback (`POST /installations/claim`) receives
`installation_id` from the client. The original implementation validated only
the intent nonce — which proves the caller started a connect flow *for their
own workspace*, not that they have any relationship with the installation they
name. GitHub App installation IDs are small sequential integers, so any
signed-up user could mint an intent and bind an arbitrary organisation's
installation to their own workspace, syncing that organisation's private
repository list and receiving its ongoing PR/deployment webhook data. This was
a critical cross-tenant data-exposure vulnerability.

## Decision

A claim binds an installation only with proof the caller controls it, and the
form of proof depends on the installation's account type:

- **User-type installations**: the installation's `account.id` (fetched from
  GitHub with the app JWT) must equal the caller's `github_account_id`. The
  callback binds immediately, as before.
- **Organisation-type installations**: the app-JWT installation fetch does not
  identify the installer, and we deliberately avoid requiring extra GitHub App
  permissions (org members read) or Clerk-brokered user OAuth tokens. The only
  GitHub-authenticated evidence of control we hold is the installation
  webhook's `sender` — so org installations bind **exclusively via webhook
  sender matching** (`claim_by_sender`). The callback answers **202 pending**
  without consuming the intent; the client polls until the webhook lands. A
  poll that finds the intent consumed *and* the installation bound to the
  intent's workspace reads as success (idempotent completion), so the
  webhook/callback race resolves cleanly in either order.

An installation already bound to the intent's workspace claims without
re-proving — re-connecting something the workspace already has grants nothing
new.

## Consequences

- Fresh org installs complete within webhook latency (normally seconds); the
  setup page shows a "waiting for GitHub" state while polling and hands over
  guidance after ~40s.
- A configure-only visit to an existing org installation that changes nothing
  fires no webhook, so it cannot complete a *new* workspace binding by itself.
  The pending-state guidance tells the user that adjusting the repository
  selection (which fires `installation_repositories`, whose sender they are)
  completes the connection. Re-binding to an already-linked workspace is
  unaffected.
- The claim endpoint distinguishes "pending" (202) from terminal errors (400);
  `GET /app/installations/{id}` failures surface as 400, not pending, so the
  client never polls a dead end.
