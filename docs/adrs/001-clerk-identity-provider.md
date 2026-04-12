# ADR 001: Clerk as Identity Provider

**Date:** 2026-03-21
**Status:** Accepted
**RFC:** [RFC 016: SaaS Tenant Creation](../rfcs/016-saas-tenant-creation.md)

## Context

Distilled needed to move from a single-tenant static API key model to a proper multi-tenant SaaS authentication system. The requirements were:

- GitHub OAuth as the only sign-in method (target users are engineers)
- No custom session management or OAuth secret handling in application code
- Self-service onboarding: a new user signs in and is automatically provisioned
- Stateless auth suitable for Railway's multi-instance deployment

## Decision

Use **Clerk** as the identity provider.

**Authentication mechanism:** Clerk issues JWTs signed with RS256. The backend verifies these tokens via JWKS fetched from a Clerk URL, cached in-process for 1 hour. No Clerk SDK is used on the backend — only standard JWT verification (`PyJWT`).

**Frontend:** `@clerk/clerk-react` provides the `<ClerkProvider>`, `<SignedIn>/<SignedOut>` gates, and `useAuth().getToken()` for attaching session tokens to API calls.

## Consequences

**Positive:**
- Application code handles no OAuth secrets, passwords, or sessions
- JWKS-based verification is stateless and works across multiple Railway instances
- GitHub as the only provider ensures all users have GitHub accounts (required for the GitHub App install flow anyway)
- Tenant auto-provisioning on first login is idempotent — no registration step

**Negative:**
- Dependency on Clerk as a third-party service
- JWKS cache is in-process per worker; if Clerk rotates keys, workers may temporarily return 401s until cache expires (TTL is 1 hour)
- Multi-worker JWKS consistency is not guaranteed, but is safe because all workers eventually converge

## Alternatives considered

**Roll our own GitHub OAuth:** Would require managing OAuth secrets, callback URLs, session storage, and CSRF protection. High complexity, high risk.

**Auth0:** Similar capability to Clerk, but more complex pricing and less developer-friendly React SDK.

**NextAuth.js:** Not applicable — backend is FastAPI, not Next.js.
