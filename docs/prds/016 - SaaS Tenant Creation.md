# SaaS Tenant Creation & Self-Service Onboarding

## Summary

Enable Distilled to operate as a true multi-tenant SaaS product. Today the system is hardwired to a single seed tenant with a shared static API key — there is no login, no user accounts, and no self-service path to get started. This PRD covers everything needed for a stranger to land on Distilled, authenticate via GitHub, have a tenant provisioned for them automatically, and be guided through connecting their first repository.

---

## Problem

Distilled's data model and API are already multi-tenant (every row carries a `tenant_id`) but the product layer is entirely absent:

- There is no login or registration flow.
- A single hardcoded API key authenticates every request.
- Tenant resolution is a stub that returns the seed UUID unconditionally.
- There is no UI path that guides a new user to connect a GitHub organisation.

This means the product cannot be used by anyone except the developer who seeded the database. Fixing this is the prerequisite for all commercial use.

---

## Goals

1. Allow any user with a GitHub account to sign up and immediately have a private Distilled tenant.
2. Replace the static API key with session-scoped authentication backed by a third-party identity provider.
3. Guide users through GitHub App installation when they have no connected repositories.
4. Support deployment on Railway cloud infrastructure without special networking or persistent local state.

---

## Non-Goals

- Email/password auth or any OAuth provider other than GitHub.
- Role-based access control or multi-user organisations (single owner per tenant for now).
- Billing, plan limits, or subscription management.
- Social sign-in (Google, LinkedIn, etc.).

---

## Users

**Primary:** An engineering leader (CTO, VP Eng, EM) who has heard of Distilled and wants to try it against their own GitHub repositories. They are technically capable but have zero patience for setup friction.

**Journey:** lands on the app → clicks "Sign in with GitHub" → authorises the app → tenant is created → sees an empty dashboard with a clear call-to-action to install the GitHub App → installs the GitHub App → repos appear → dashboard populates.

---

## Identity Provider

Use **Clerk** as the third-party identity provider. Clerk satisfies every constraint:

- Hosted OAuth flow so no credentials or sessions are managed in application code.
- Native GitHub-only configuration (other providers can be disabled in the Clerk dashboard).
- JWT-based session tokens that are stateless and work across Railway's ephemeral compute.
- SDKs for both FastAPI (via `clerk-backend-api` or JWKS verification) and React (`@clerk/clerk-react`).
- No persistent local state required — all session state lives in Clerk's infrastructure.
- Railway-compatible: only requires `CLERK_SECRET_KEY` and `CLERK_PUBLISHABLE_KEY` environment variables and optionally a custom domain.

**Alternative considered:** Auth0, Supabase Auth, WorkOS. All viable. Clerk is preferred because it ships a production-ready `<SignIn>` component, the JWKS endpoint is trivially consumed in FastAPI, and pricing is generous at the scale this product will operate initially.

---

## Authentication Flow

```
Browser                   Clerk                     FastAPI
  │                          │                          │
  │── click "Sign in" ──────►│                          │
  │                          │── GitHub OAuth ──────────│
  │◄─ Clerk session JWT ─────│                          │
  │                          │                          │
  │── API request (Authorization: Bearer <jwt>) ────────►│
  │                          │                  verify JWT via JWKS
  │                          │                  extract clerk_user_id
  │                          │                  resolve or create tenant
  │◄─────────────────────────────── response ───────────│
```

- The client uses `@clerk/clerk-react` to render the sign-in widget and attach the session JWT to every API request.
- The backend verifies the JWT against Clerk's JWKS endpoint (`https://<clerk-domain>/.well-known/jwks.json`) — no shared secret, no database round-trip for auth.
- On first request from a new Clerk user ID, the backend auto-provisions a `Tenant` and a `User` record (with `clerk_user_id` as the stable identifier).

---

## Data Model Changes

### New: `users` table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | internal identifier |
| `clerk_user_id` | TEXT UNIQUE NOT NULL | stable ID from Clerk (`user_xxx`) |
| `email` | TEXT | synced from Clerk at first login |
| `github_username` | TEXT | synced from Clerk GitHub account |
| `tenant_id` | UUID FK → tenants | owner of this tenant |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

> One user : one tenant for now. The tenant is created at first login and is permanently associated with the user.

### Modified: `tenants` table

Add `slug` (TEXT UNIQUE) derived from the user's GitHub username or org name — used in display and future URL routing.

---

## Backend Changes

### JWT Middleware

Replace the current `HTTPBearer` API key check in `auth.py` with a JWT verification layer:

1. Extract `Authorization: Bearer <token>` header.
2. Fetch and cache Clerk's JWKS (refresh on 401 from GitHub, TTL 1 h).
3. Decode and validate the JWT (signature, expiry, issuer).
4. Extract `sub` (Clerk user ID) from claims.
5. Inject `current_user` into the request dependency graph.

### Tenant Auto-Provisioning

Replace the stub in `middleware/tenant.py` with real resolution:

1. Look up `User` by `clerk_user_id`.
2. If found → return `tenant_id`.
3. If not found → create `Tenant` + `User` in a transaction → return new `tenant_id`.

This is idempotent and requires no explicit registration step from the user.

### GitHub Installation → Tenant Linkage

When a `installation:created` webhook fires, the current code uses the seed tenant. After this change:

- The webhook payload contains a GitHub `account.login` (org or user).
- Match this to the `github_username` stored on the `User` record.
- Link the installation to the matched tenant.

This means users must sign in before installing the GitHub App so the username is recorded. The onboarding flow enforces this ordering.

### Removal of Static API Key Auth

The `API_KEY` environment variable and all related code is removed. All clients must use Clerk session JWTs. The dev seed tenant remains for local development but accessed via a dev Clerk account, not a shared key.

---

## Frontend Changes

### Auth Wrapper

Wrap the entire React app in `<ClerkProvider>`. Unauthenticated users see only the sign-in page. Authenticated users see the dashboard (or onboarding).

```
<ClerkProvider publishableKey={...}>
  <SignedOut>  → <SignInPage />        </SignedOut>
  <SignedIn>   → <App />               </SignedIn>
</ClerkProvider>
```

### API Client

Modify the Axios/fetch layer to attach the Clerk session JWT on every request:

```ts
const token = await getToken();  // Clerk hook
headers['Authorization'] = `Bearer ${token}`;
```

### Sign-In Page

Minimal, on-brand page using Clerk's `<SignIn>` component. Dark background, centred card. GitHub is the only shown provider. No email/password fields.

---

## Onboarding Flow

When an authenticated user has zero repositories connected, show an **Onboarding Screen** in place of the dashboard.

### Empty State → Setup Screen

**Trigger:** `GET /api/repos` returns an empty array for the authenticated tenant.

**Screen layout:**

```
┌────────────────────────────────────────────────────┐
│  Welcome to Distilled                              │
│                                                    │
│  Connect your GitHub repositories to start         │
│  tracking your engineering delivery metrics.       │
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  Step 1: Install the Distilled GitHub App    │  │
│  │  Grant access to the repositories you want  │  │
│  │  to track. You can add more repos later.    │  │
│  │                                              │  │
│  │  [Install GitHub App →]                     │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  Already installed? Waiting for data…              │
│  Repos appear here within a few seconds of        │
│  completing the GitHub App installation.           │
└────────────────────────────────────────────────────┘
```

### Install CTA

The "Install GitHub App" button links directly to the GitHub App installation URL (`https://github.com/apps/<app-slug>/installations/new`). This opens GitHub in a new tab.

### Post-Install Detection

After the user installs the GitHub App, GitHub sends an `installation:created` webhook to the backend. The frontend should poll `GET /api/repos` every 5 seconds while on the setup screen. When repos appear, transition to the dashboard automatically.

### Subsequent Visits

Once repositories exist, the setup screen is never shown again. The dashboard is the landing page.

---

## Railway Deployment Compatibility

- **Stateless sessions:** Clerk JWTs are self-contained — no sticky sessions, no Redis, no shared session store needed.
- **JWKS caching:** Cache Clerk's JWKS in memory per process. Railway may run multiple instances; this is fine because JWKS keys are the same across all Clerk instances and rarely rotate.
- **Environment variables:** Only `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, and `CLERK_JWKS_URL` required. All set as Railway service variables.
- **No persistent filesystem:** Nothing auth-related writes to disk.
- **CORS:** The backend's allowed origins list must include the Railway-deployed frontend URL (set via `ALLOWED_ORIGINS` env var).
- **Webhook endpoint:** Already public and HMAC-verified. No change needed for Railway.

---

## Acceptance Criteria

### Authentication
- [ ] A new user can click "Sign in with GitHub" and be authenticated within 2 OAuth steps.
- [ ] Authenticated API requests succeed; unauthenticated requests return 401.
- [ ] Two different GitHub accounts receive different tenant IDs and cannot see each other's data.
- [ ] Signing out clears the session and returns the user to the sign-in page.

### Tenant Provisioning
- [ ] A `Tenant` and `User` record are created automatically on first successful login.
- [ ] Repeat logins do not create duplicate tenants or users.
- [ ] The `github_username` on the user record matches the authenticated GitHub account.

### GitHub Installation Linkage
- [ ] After installing the GitHub App, the `GitHubInstallation` is linked to the correct tenant.
- [ ] Installing the app before signing in shows an appropriate error or holds gracefully.

### Onboarding
- [ ] A tenant with no repos sees the setup screen, not the dashboard.
- [ ] The "Install GitHub App" button opens GitHub App installation in a new tab.
- [ ] After installation, the frontend detects new repos and transitions to the dashboard without a manual refresh.
- [ ] A tenant with at least one repo never sees the setup screen.

### Railway Compatibility
- [ ] The application starts and handles auth correctly with only env vars (no local files).
- [ ] Multiple backend instances can process requests from the same user without session conflicts.

---

## Open Questions

1. **GitHub App slug:** What is the production GitHub App name/slug? This is needed for the install URL in onboarding. If it differs between environments, it should be a configurable env var (`GITHUB_APP_SLUG`).

2. **Clerk domain:** Will we use the default Clerk subdomain (`xxx.clerk.accounts.dev`) or a custom domain? Custom domain is cleaner for production and removes the Clerk branding from OAuth consent screens.

3. **Webhook → tenant matching on username:** GitHub usernames are mutable. Should we also store the GitHub numeric user ID from the Clerk identity for a more stable match? Recommendation: yes — store both.

4. **Existing seed data:** The dev seed tenant (UUID `000...001`) must remain functional for local development. What is the expected dev workflow after this change — a local Clerk dev account, or a flag to bypass auth in `DEBUG` mode?
