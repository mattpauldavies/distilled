# RFC 016: SaaS Tenant Creation & Self-Service Onboarding

## Summary

Replace the hardcoded single-tenant model with a real multi-tenant SaaS authentication and onboarding system. A stranger with a GitHub account lands on Distilled, clicks "Sign in with GitHub", is authenticated via Clerk, has a tenant automatically provisioned, and is guided through installing the GitHub App to connect their repositories.

The three pillars: Clerk-backed JWT authentication replaces the static API key; auto-provisioning creates a `Tenant` and `User` on first login; an onboarding screen guides new tenants from zero repos to a live dashboard.

---

## Context

The current state of the product:

- `server/app/auth.py` — `require_api_key` checks a static `Authorization: Bearer <key>` from `settings.api_key`
- `server/app/middleware/tenant.py` — `get_tenant_id()` unconditionally returns the seed UUID from settings
- `server/app/models/tenant.py` — `Tenant` has only `id` and `name`; no user concept exists
- `server/app/services/installation_service.py:29` — hardcodes `uuid.UUID(settings.seed_tenant_id)` for all webhook events
- `client/src/lib/api.ts` — `apiFetch` attaches `Authorization: Bearer ${VITE_API_KEY}`
- `client/src/App.tsx` — renders `<Dashboard />` directly with no auth gate

The data model is already multi-tenant (every row has `tenant_id`), but the product layer is entirely absent.

---

## Decisions

The PRD posed four open questions; all are resolved:

1. **GitHub App slug** → configurable via `GITHUB_APP_SLUG` env var (differs between environments)
2. **Clerk domain** → configurable via `CLERK_JWKS_URL` env var; start with the default Clerk subdomain
3. **Webhook → tenant matching** → store the GitHub numeric account ID (`github_account_id`) for stable matching rather than the mutable username
4. **Dev workflow** → a local Clerk dev account; the seed tenant remains for local development

---

## Architecture

### Identity Provider: Clerk

Clerk is used as the identity provider. The application code never handles OAuth secrets, user passwords, or session management. The only Clerk artefacts in application code are:

- **Backend:** JWKS-based JWT verification (`CLERK_JWKS_URL`)
- **Frontend:** `@clerk/clerk-react` for the sign-in widget and session token retrieval

### Auth Flow

```
Browser                   Clerk                     FastAPI
  │                          │                          │
  │── click "Sign in" ──────►│                          │
  │                          │── GitHub OAuth ──────────│
  │◄─ session JWT ───────────│                          │
  │                          │                          │
  │── GET /api/repos (Authorization: Bearer <jwt>) ─────►│
  │                          │            verify JWT via JWKS
  │                          │            extract clerk_user_id (sub)
  │                          │            resolve or create tenant
  │◄─────────────────────────────── 200 ────────────────│
```

### Tenant Auto-Provisioning

On first authenticated request from a new Clerk user ID:
1. Look up `User` by `clerk_user_id`
2. Not found → create `Tenant` + `User` in a transaction → return `tenant_id`
3. Found → return existing `tenant_id`

This is idempotent. No explicit registration step.

---

## Data Model Changes

### New: `users` table

```python
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: UUID PK
    clerk_user_id: TEXT UNIQUE NOT NULL    # stable Clerk identifier ("user_xxx")
    email: TEXT                            # synced from Clerk at first login
    github_username: TEXT                  # mutable, display only
    github_account_id: BIGINT UNIQUE       # stable numeric GitHub ID
    tenant_id: UUID FK → tenants.id
```

`github_account_id` is used for webhook → tenant matching (stable; `github_username` is mutable).

### Modified: `tenants` table

Add `slug TEXT UNIQUE` — derived from GitHub username at provisioning time, used for display and future URL routing.

```sql
ALTER TABLE tenants ADD COLUMN slug TEXT UNIQUE;
```

### Migration

A single Alembic migration file that:
1. Adds `slug` to `tenants`
2. Creates the `users` table with the above columns

---

## Backend Changes

### 1. New: `server/app/services/clerk_service.py`

Handles JWKS caching and JWT verification:

```python
class ClerkJWTVerifier:
    """Fetches and caches Clerk JWKS; validates incoming JWTs."""
    _jwks: dict | None = None
    _fetched_at: datetime | None = None
    _ttl: int = 3600  # 1 hour

    async def get_jwks(self) -> dict: ...
    async def verify_token(self, token: str) -> dict:
        """Returns decoded claims dict. Raises HTTPException(401) on failure."""
```

JWKS is cached in-process with a 1-hour TTL. Railway may run multiple instances; this is safe because Clerk's JWKS keys are identical across all processes for a given Clerk instance.

### 2. Replace `server/app/auth.py`

Remove `require_api_key`. Replace with `require_auth` that:

1. Extracts `Authorization: Bearer <jwt>` via `HTTPBearer`
2. Calls `ClerkJWTVerifier.verify_token(token)` — returns claims or raises 401
3. Extracts `sub` (Clerk user ID) from claims
4. Calls `get_or_create_user_and_tenant(clerk_user_id, email, github_username, github_account_id, session)` which returns a `(User, Tenant)` tuple
5. Returns `CurrentUser` dataclass (user + tenant) injected into the dependency graph

```python
async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    claims = await verifier.verify_token(credentials.credentials)
    return await get_or_create_user_and_tenant(claims, session)
```

### 3. Replace `server/app/middleware/tenant.py`

`get_tenant_id()` becomes a dependency on `require_auth`:

```python
async def get_tenant_id(current_user: CurrentUser = Depends(require_auth)) -> uuid.UUID:
    return current_user.tenant_id
```

All existing routes that depend on `get_tenant_id` inherit auth automatically — no per-route changes needed.

### 4. New: `server/app/services/user_service.py`

```python
async def get_or_create_user_and_tenant(
    claims: dict,
    session: AsyncSession,
) -> CurrentUser:
    """
    Idempotent. On first call for a clerk_user_id, creates Tenant + User in one
    transaction. On subsequent calls, returns the existing records.
    """
```

Extracts from Clerk JWT claims:
- `sub` → `clerk_user_id`
- `email` (from `email_addresses[0]` or `email` claim)
- GitHub metadata from `external_accounts` array: `username`, `provider_user_id` (numeric GitHub ID)

### 5. Modify `server/app/services/installation_service.py`

Replace the hardcoded `tenant_id = uuid.UUID(settings.seed_tenant_id)` with a lookup:

```python
# Match installation to tenant by GitHub account ID
github_account_id = installation_data["account"]["node_id"]  # numeric id in payload as int
# Or use: installation_data["account"]["id"]

user = await session.execute(
    select(User).where(User.github_account_id == installation_data["account"]["id"])
)
user = user.scalar_one_or_none()

if user is None:
    logger.warning(
        "installation:created received for unknown github account %s — skipping",
        installation_data["account"]["login"],
    )
    return

tenant_id = user.tenant_id
```

If no matching user exists (installed before sign-in), the installation is held gracefully with a warning log. The user can re-install after signing in.

### 6. Remove `API_KEY` config field

Remove `api_key: str = ""` from `server/app/config.py`. Add new fields:

```python
clerk_jwks_url: str = ""       # e.g. https://xxx.clerk.accounts.dev/.well-known/jwks.json
clerk_publishable_key: str = ""  # used only in health check / debugging
github_app_slug: str = ""      # e.g. "distilled-app" for onboarding install URL
```

### 7. Modify `server/app/main.py`

Replace `Depends(require_api_key)` with `Depends(require_auth)` on all protected routers. The webhook and health routes remain unauthenticated.

---

## Frontend Changes

### 1. Install `@clerk/clerk-react`

```bash
npm install @clerk/clerk-react
```

### 2. New env var: `VITE_CLERK_PUBLISHABLE_KEY`

Add to `client/.env.example`. Remove `VITE_API_KEY`.

### 3. Modify `client/src/main.tsx`

Wrap the app in `<ClerkProvider>`:

```tsx
import { ClerkProvider } from "@clerk/clerk-react"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClerkProvider publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY}>
      <App />
    </ClerkProvider>
  </StrictMode>
)
```

### 4. Modify `client/src/App.tsx`

Gate the app behind Clerk's `<SignedIn>` / `<SignedOut>`:

```tsx
import { SignedIn, SignedOut } from "@clerk/clerk-react"
import { SignInPage } from "@/components/SignInPage"

export default function App() {
  return (
    <ErrorBoundary>
      <SignedOut>
        <SignInPage />
      </SignedOut>
      <SignedIn>
        <Dashboard />
      </SignedIn>
    </ErrorBoundary>
  )
}
```

### 5. New: `client/src/components/SignInPage.tsx`

Minimal, on-brand sign-in page using Clerk's `<SignIn>` component. Dark background, centred card, GitHub as the only provider.

```tsx
import { SignIn } from "@clerk/clerk-react"

export function SignInPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <SignIn
        appearance={{ variables: { colorBackground: "var(--color-surface)" } }}
      />
    </main>
  )
}
```

### 6. Modify `client/src/lib/api.ts`

Replace static API key with Clerk session token:

```ts
import { useAuth } from "@clerk/clerk-react"

// apiFetch becomes a hook-aware function.
// Since hooks can't be called in plain functions, expose a factory:
export function makeApiFetch(getToken: () => Promise<string | null>) {
  return async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
    const token = await getToken()
    return fetch(input, {
      ...init,
      headers: {
        ...init?.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  }
}
```

Hooks (`useDashboard`, `useRepos`) are updated to call `useAuth().getToken()` and pass it to `makeApiFetch`.

### 7. New: `client/src/components/OnboardingScreen.tsx`

Shown when `GET /api/repos` returns an empty array. Polls every 5 seconds. Transitions to the dashboard when repos appear.

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

Install URL: `https://github.com/apps/${VITE_GITHUB_APP_SLUG}/installations/new`

### 8. Modify `client/src/components/Dashboard.tsx`

Replace the current empty-repos fallback (`<p>No repositories found</p>`) with `<OnboardingScreen />`. Add a sign-out button in the header.

---

## New Environment Variables

### Backend (`server/.env`)

| Variable | Required | Notes |
|---|---|---|
| `CLERK_JWKS_URL` | Yes | e.g. `https://xxx.clerk.accounts.dev/.well-known/jwks.json` |
| `GITHUB_APP_SLUG` | Yes | e.g. `distilled-app` |
| `API_KEY` | **Remove** | Replaced by Clerk JWT auth |

### Frontend (`client/.env`)

| Variable | Required | Notes |
|---|---|---|
| `VITE_CLERK_PUBLISHABLE_KEY` | Yes | e.g. `pk_test_xxx` |
| `VITE_GITHUB_APP_SLUG` | Yes | Same value as backend `GITHUB_APP_SLUG` |
| `VITE_API_KEY` | **Remove** | Replaced by Clerk session token |

---

## Test Strategy

### Backend

- **`server/tests/test_auth.py`** (replace existing): Tests for `require_auth` — missing header → 403, invalid JWT → 401, valid JWT → injects `CurrentUser`
- **`server/tests/test_user_service.py`** (new): Tests for `get_or_create_user_and_tenant` — first call creates records, second call returns same records (idempotency)
- **`server/tests/test_installation_service.py`** (new): Tests for installation → tenant matching — known user matches, unknown user logs warning and returns gracefully
- **`server/tests/conftest.py`** (update): Override `require_auth` (not `require_api_key`) in all test fixtures; inject a test `CurrentUser`

### Frontend

- **`client/src/hooks/useRepos.test.ts`** (update): Mock `useAuth` to return a token; assert `Authorization: Bearer <token>` header is sent
- **`client/src/hooks/useDashboard.test.ts`** (update): Same as above
- **`client/src/components/OnboardingScreen.test.tsx`** (new): Empty repos → renders onboarding; after repos appear → calls transition callback; install button has correct URL
- **`client/src/components/Dashboard.test.tsx`** (update): With repos → renders dashboard; no repos → renders `<OnboardingScreen />`

---

## Railway Compatibility

- **Stateless:** Clerk JWTs are self-contained — no sticky sessions, no Redis
- **JWKS caching:** In-process per worker; safe because JWKS keys are identical across all Clerk instances and rotate rarely
- **No filesystem writes:** Nothing auth-related touches disk
- **CORS:** `ALLOWED_ORIGINS` env var already covers the Railway frontend URL

---

## Out of Scope

- Multi-user organisations (single owner per tenant for this RFC)
- Billing, plan limits, subscription management
- Any OAuth provider other than GitHub
- Moving JWKS cache to Redis for multi-worker consistency (separate RFC if needed)
- Async webhook processing / dead-letter queue (RFC 015 deferred item)

---

## Implementation Plan

### Phase 1: Database migrations

- [ ] **1.1** Create Alembic migration: add `slug TEXT UNIQUE` to `tenants`
- [ ] **1.2** Same migration: create `users` table (`id`, `clerk_user_id`, `email`, `github_username`, `github_account_id`, `tenant_id`, timestamps)
- [ ] **1.3** Create `server/app/models/user.py` SQLAlchemy model matching the migration
- [ ] **1.4** Update `server/app/models/__init__.py` to export `User`
- [ ] **1.5** Add `slug` field to `server/app/models/tenant.py`
- [ ] **1.6** Run migration in dev and verify schema

---

### Phase 2: Backend JWT auth + user service

- [ ] **2.1** Write failing tests in `server/tests/test_clerk_service.py` for JWKS caching and token verification
- [ ] **2.2** Create `server/app/services/clerk_service.py` — `ClerkJWTVerifier` with `get_jwks` and `verify_token`
- [ ] **2.3** Write failing tests in `server/tests/test_user_service.py` for `get_or_create_user_and_tenant` (first call, idempotent second call)
- [ ] **2.4** Create `server/app/services/user_service.py` — `get_or_create_user_and_tenant`
- [ ] **2.5** Write failing tests in `server/tests/test_auth.py` for `require_auth` (missing header → 403, bad JWT → 401, valid JWT → CurrentUser)
- [ ] **2.6** Replace `server/app/auth.py` — remove `require_api_key`, add `require_auth` and `CurrentUser` dataclass
- [ ] **2.7** Add `clerk_jwks_url` and `github_app_slug` to `server/app/config.py`; remove `api_key`
- [ ] **2.8** Run all backend tests — expect `test_auth.py` tests to pass; fix any regressions

---

### Phase 3: Tenant resolution via auth

- [ ] **3.1** Replace `server/app/middleware/tenant.py` — `get_tenant_id` delegates to `require_auth`
- [ ] **3.2** Update `server/app/main.py` — replace `Depends(require_api_key)` with `Depends(require_auth)` on all protected routers
- [ ] **3.3** Update `server/tests/conftest.py` — override `require_auth` (inject test `CurrentUser`) instead of `require_api_key`; remove `get_tenant_id` override
- [ ] **3.4** Run full server test suite — all tests should pass

---

### Phase 4: Installation → tenant linkage

- [ ] **4.1** Write failing tests in `server/tests/test_installation_service.py` — known GitHub account ID matches tenant; unknown account ID logs warning and returns gracefully
- [ ] **4.2** Modify `server/app/services/installation_service.py:_handle_created` — replace hardcoded seed `tenant_id` with `User` lookup by `github_account_id`
- [ ] **4.3** Run installation service tests — all should pass
- [ ] **4.4** Run full server test suite — all should pass

---

### Phase 5: Frontend auth integration

- [ ] **5.1** Install `@clerk/clerk-react` — `cd client && npm install @clerk/clerk-react`
- [ ] **5.2** Add `VITE_CLERK_PUBLISHABLE_KEY` and `VITE_GITHUB_APP_SLUG` to `client/.env.example`; remove `VITE_API_KEY`
- [ ] **5.3** Wrap `client/src/main.tsx` in `<ClerkProvider publishableKey={...}>`
- [ ] **5.4** Create `client/src/components/SignInPage.tsx` — dark centred card with Clerk `<SignIn>` component
- [ ] **5.5** Update `client/src/App.tsx` — add `<SignedIn>` / `<SignedOut>` gates, render `<SignInPage />` for unauthenticated users
- [ ] **5.6** Rewrite `client/src/lib/api.ts` — `makeApiFetch(getToken)` factory that attaches Clerk session token
- [ ] **5.7** Update `client/src/hooks/useRepos.ts` — use `useAuth().getToken` with `makeApiFetch`
- [ ] **5.8** Update `client/src/hooks/useDashboard.ts` — use `useAuth().getToken` with `makeApiFetch`
- [ ] **5.9** Update `client/src/hooks/useRepos.test.ts` — mock `useAuth`; assert `Authorization: Bearer <token>` header
- [ ] **5.10** Update `client/src/hooks/useDashboard.test.ts` — same
- [ ] **5.11** Run client tests — all should pass

---

### Phase 6: Onboarding screen

- [ ] **6.1** Write failing tests in `client/src/components/OnboardingScreen.test.tsx` — renders on empty repos, install button has correct URL, polling detects new repos
- [ ] **6.2** Create `client/src/components/OnboardingScreen.tsx` — onboarding UI with polling (`setInterval` every 5s), install GitHub App CTA, auto-transition when repos appear
- [ ] **6.3** Update `client/src/components/Dashboard.tsx` — replace `<p>No repositories found</p>` with `<OnboardingScreen onReposDetected={...} />`; add sign-out button
- [ ] **6.4** Update `client/src/components/Dashboard.test.tsx` — add tests for onboarding / dashboard routing based on repos
- [ ] **6.5** Run full client test suite — all should pass

---

### Phase 7: Documentation and verification

- [ ] **7.1** Update `server/.env.example` — add `CLERK_JWKS_URL`, `GITHUB_APP_SLUG`; remove `API_KEY`
- [ ] **7.2** Update `client/.env.example` — add `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_GITHUB_APP_SLUG`; remove `VITE_API_KEY`
- [ ] **7.3** Update `server/README.md` and `client/README.md` with new env var setup
- [ ] **7.4** Update `docs/adrs/` with an ADR documenting the Clerk identity provider decision
- [ ] **7.5** Run full test suite (server + client) — all pass
- [ ] **7.6** Smoke test locally: sign in with Clerk dev account, tenant provisioned, onboarding screen shown, install GitHub App, repos appear, dashboard loads
