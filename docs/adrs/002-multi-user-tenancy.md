# ADR 002: Multi-User Tenancy via `tenant_users` Membership Join

**Date:** 2026-05-05
**Status:** Accepted
**RFC:** [RFC 021: Multi-User Tenants & Account Sharing](../rfcs/021-multi-user-tenants.md)

## Context

ADR 001 established a 1:1 mapping between Clerk users and tenants — `User.tenant_id` was a NOT-NULL FK and every authenticated request inferred its tenant from the user. This was right for solo onboarding but blocked every realistic team workflow: an owner couldn't bring teammates into the same tenant, a user couldn't belong to more than one tenant, and there was no concept of an "owner" distinct from a "member" for guarding destructive actions.

We needed:

- Multiple users per tenant
- Multiple tenants per user
- An explicit owner role
- A way to switch between tenants without per-tenant sign-in
- Invitations over GitHub-only sign-in (Clerk's invite primitive doesn't extend cleanly)

## Decision

**Membership** is modelled as a dedicated `tenant_users` join table with `(user_id, tenant_id, role)`. The `users.tenant_id` column is dropped. Every membership row carries `role IN ('owner','member')`, with a partial unique index `WHERE role = 'owner'` enforcing exactly one owner per tenant at the database level.

**Active tenant** is a per-request concern, not a per-user state. The client sends `X-Tenant-Id` on every authenticated request; the backend verifies membership and resolves `(tenant, role)` for the route. When the header is absent, the backend falls back to `users.last_active_tenant_id` (a nullable column added for this purpose) so a fresh sign-in lands the user where they were before. The active tenant is lazily persisted on each authenticated request when it changes.

**Invitations** use opaque 32-byte URL-safe tokens. Only the SHA-256 hash is stored in `invitations.token_hash`; the raw token leaves the server exactly once, in the email body. Redemption is bundled into the first sign-in: the user clicks the link, signs in with GitHub (any GitHub account — the email on the GitHub identity is irrelevant), and the page auto-fires `POST /invitations/redeem` with the token. There is no preview step.

**Email delivery** sits behind a small `EmailService` Protocol with two implementations: `ResendEmailService` (production) and `LoggingEmailService` (dev/tests). This decouples invitation logic from the provider so future product mail (digests, billing receipts) can fan out without rewiring identity.

**Cascade cleanup.** All tenant-scoped FKs (`repositories`, `pull_requests`, `deployment_events`, `tenant_users`, `invitations`, the metrics tables) carry `ON DELETE CASCADE`, so deleting a tenant is a single SQL statement.

## Consequences

**Positive:**

- A user can belong to many tenants; tenants can have many users. The product layer matches the real organisational shape that customers expect.
- The one-owner invariant is enforced by the database (partial unique index), not application code. There is no "no owner" or "two owners" state at any point of an ownership transfer.
- Per-request tenant resolution means a single Clerk session can drive multiple tenants in different tabs without per-tenant sign-in.
- Token-as-credential redemption keeps GitHub-only sign-in viable: invitees don't need the GitHub account on the email address that received the invite.
- Tenant deletion is atomic: one `DELETE FROM tenants WHERE id = ...` cleans every dependent row.

**Negative:**

- Every authenticated request now executes one extra query (membership join). Mitigated by: (a) the join is on indexed columns, (b) it replaces the previous direct lookup, so the per-request cost is similar.
- `X-Tenant-Id` adds a header dependency for clients. The frontend handles this in one place (`useApiFetch` in `client/src/lib/tenantContext.tsx`); other API consumers must remember to send it.
- The two-step invitation flow (banner accept vs. token redeem) means we keep two codepaths for joining a tenant.
- Email delivery introduces a new external dependency (Resend) with its own failure modes. The Protocol-based abstraction limits the blast radius if we need to swap providers.

## Alternatives considered

**Org-style tenants in Clerk.** Clerk's organizations primitive could model membership, but coupling tenant identity to Clerk creates portability risk and binds invitation lifecycles to Clerk's email pipeline. We chose to keep tenant data sovereign in our DB and let Clerk own only identity.

**Naming convention `tenant_memberships`.** Rejected during RFC review in favour of the more concrete `tenant_users` — matches the codebase's existing plural-noun table style (`webhook_events`, `pull_requests`, etc.) and reads as "the join between tenants and users" rather than introducing a new abstract noun.

**Two-step migration (memberships first, then drop column).** Initially considered for safety, but Railway runs migrations inline with code deploy — the staged rollout buys nothing because both halves run together. Consolidated into a single revision (`c1d2e3f4a5b6_multi_user_tenants`).

**Invitation preview endpoint.** A `GET /invitations/preview` was considered to surface tenant + inviter pre-sign-in, but the user has already read both in the email. We dropped it during RFC review.
