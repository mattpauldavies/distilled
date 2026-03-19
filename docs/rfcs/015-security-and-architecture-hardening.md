# RFC 014: Security and Architecture Hardening

## Summary

A comprehensive security and architecture review identified several critical vulnerabilities and structural weaknesses that must be addressed before Distilled can be exposed to any real user traffic or production data. This RFC documents all findings and proposes a phased remediation plan.

The three-sentence summary: the API is entirely unauthenticated and exposes all data to any caller; CORS is wide open which compounds that risk; and a logic bug means webhook signature verification can be bypassed when the secret is absent. These three issues alone constitute a P0 production blocker. The remaining findings range from high to informational and should be resolved in the weeks following.

---

## Findings

### Critical (P0 — Fix Before Any Production Use)

#### CRIT-001 — No Authentication on Any API Endpoint

**File:** `server/app/main.py`, all router includes

Every route — `/api/repos`, `/api/metrics/*`, `/api/deployments/*`, `/api/pull-requests/*`, `/api/environments/*` — is fully open with zero authentication middleware. No bearer token, no session, no API key. Any unauthenticated HTTP client can read all data. The `PATCH /api/environments/{env_id}` endpoint also allows mutation of production environment configuration without any credentials.

**Proposed fix:** Add a static API key guard as an immediate stopgap (see design below). Long-term, migrate to OIDC/JWT once multi-tenant auth is designed.

---

#### CRIT-002 — Wildcard CORS

**File:** `server/app/main.py`, lines 36–41

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    ...
)
```

`allow_origins=["*"]` combined with no authentication means any web page loaded in a visitor's browser can silently read all API data cross-origin. This must be scoped to known origins.

**Proposed fix:** Replace `["*"]` with an explicit list sourced from settings (e.g. `settings.allowed_origins: list[str]`).

---

#### CRIT-003 — Webhook Signature Bypass When Secret Is Empty

**File:** `server/app/services/webhook_service.py`, line 18

```python
hmac.new(settings.github_webhook_secret.encode(), payload, sha256)
```

When `github_webhook_secret` is an empty string (the default dev value), this produces a valid, predictable HMAC over an empty key. An attacker who controls the request body can compute the exact signature and POST arbitrary events. `hmac.compare_digest` correctly prevents timing attacks, but the empty-secret path makes verification trivially bypassable.

**Proposed fix:** Add a guard at the top of `verify_signature`:

```python
if not secret:
    return False
```

---

### High Severity (P1)

#### HIGH-001 — Tenant ID Hardcoded in Webhook Write Path

**Files:** `server/app/services/installation_service.py` line 28, `server/app/services/deployment_service.py` lines 26 and 107

The write path hardcodes `uuid.UUID("00000000-0000-0000-0000-000000000001")` directly instead of routing through `settings.seed_tenant_id`. The query layer correctly uses the settings value; the write layer does not. These two diverge silently if multi-tenancy is ever enabled, creating a scenario where reads and writes target different tenants.

**Proposed fix:** Replace all inline UUID literals with `settings.seed_tenant_id`.

---

#### HIGH-002 — GitHub Token Cache Is Process-Local and Expiry-Unsafe

**File:** `server/app/services/github_client.py`, line 35

`GitHubClient` is instantiated fresh per webhook event, so `_token_cache` is discarded after each invocation — the cache never actually caches anything. Additionally, the expiry check uses `< expires_at` with no safety margin, meaning a token could be used in the window between the check and the API call expiring it.

**Proposed fix:** Move `_token_cache` to module level (or a shared cache) and apply a 60-second safety buffer: `< expires_at - timedelta(seconds=60)`.

---

#### HIGH-003 — No Security Headers

No security headers are set on any response: no `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `Referrer-Policy`, or `Content-Security-Policy`.

**Proposed fix:** Add a response middleware that sets the standard secure defaults on every non-webhook response.

---

#### HIGH-004 — Unvalidated URLs from GitHub Payloads Stored and Returned

**File:** `server/app/services/deployment_service.py`, lines 74 and 156

`target_url` and `html_url` are stored directly from webhook JSON and returned through the API to the frontend without validation. If GitHub were compromised or a webhook were spoofed, an attacker could inject arbitrary URLs that the frontend renders as links.

**Proposed fix:** Validate that these values start with `https://github.com/` before storing. Reject the field (set to `None`) if validation fails.

---

#### HIGH-005 — `/api/metrics/recompute` Accepts Caller-Supplied Tenant and Repo IDs

A leaked cron secret allows targeted resource exhaustion by POSTing arbitrary `tenant_id` and `repo_id` values to the recompute endpoint.

**Proposed fix:** The recompute endpoint should derive the tenant from the authenticated context rather than accepting it in the request body.

---

### Medium Severity (P2)

#### MED-001 — Database Password in `alembic.ini`

`alembic.ini` line 89 contains a hardcoded database URL including a password committed to version control. Replace with an environment variable reference: `sqlalchemy.url = %(DATABASE_URL)s`.

---

#### MED-002 — Hardcoded PostgreSQL Password in `docker-compose.yml`

`docker-compose.yml` line 9 sets `POSTGRES_PASSWORD` to a hardcoded value. Replace with a reference to an `.env` file or a Docker secret.

---

#### MED-003 — No Request Body Size Limit on Webhook Endpoint

The webhook endpoint has no body size limit. A large payload can consume disproportionate memory or CPU during JSON parsing.

**Proposed fix:** Add a FastAPI middleware or Starlette `MaxBodySize` limit (e.g. 1 MB) scoped to the webhook route.

---

#### MED-004 — No Rate Limiting on Any Endpoint

All endpoints are unbounded. Combined with no authentication, this makes the API trivially DoS-able.

**Proposed fix:** Add `slowapi` or a similar rate-limiting middleware with conservative per-IP defaults.

---

#### MED-005 — Webhook Handler Does Not Handle Malformed JSON

`request.json()` in the webhook handler will raise an unhandled exception if the body is not valid JSON, returning a 500 rather than a 400.

**Proposed fix:** Wrap in a try/except and return `400 Bad Request`.

---

#### MED-006 — React Error Boundary Logs Full Stack Traces in Production

**File:** `client/src/components/ErrorBoundary.tsx`

`console.error` with full component stacks is called unconditionally. In production builds this leaks internal component hierarchy to the browser console, which aids an attacker doing client-side reconnaissance.

**Proposed fix:** Guard with `if (process.env.NODE_ENV !== 'production')` or send errors to an error tracking service (e.g. Sentry) rather than the console.

---

### Architecture Concerns

#### ARCH-001 — Authentication Design Gap

There is no authentication design documented anywhere in the codebase. Before implementing any auth mechanism, the team should decide: static API key (simplest, suitable for single-org use), or OIDC/JWT (required for multi-tenant SaaS). The immediate fix (CRIT-001) uses a static key; a proper design should follow.

---

#### ARCH-002 — Multi-Tenant Schema, Single-Tenant Write Path

The database schema enforces `tenant_id` on all tables and the read path respects it. The write path (webhook handlers) bypasses this entirely with a hardcoded UUID. These need to be unified before multi-tenancy becomes real.

---

#### ARCH-003 — Installation Token Cache Is Not Safe for Multi-Worker Deployments

`_token_cache` is in-process. With multiple uvicorn workers, each worker maintains its own token, multiplying GitHub API calls and potentially exhausting installation token quota. Should use Redis or the database as a shared token store.

---

#### ARCH-004 — Webhook Processing Is Synchronous with No Retry or Dead-Letter Queue

Webhook events are processed synchronously in the HTTP request lifecycle. A slow database or GitHub API call can cause GitHub to time out and retry the webhook, creating duplicate processing. Failed events are silently lost with no retry mechanism or dead-letter queue.

**Future direction:** Move webhook processing to a background task queue (e.g. Celery + Redis, or PostgreSQL-backed with `pgqueue`). This is non-trivial and should be a separate RFC.

---

#### ARCH-005 — SQLAlchemy Engine Missing Resilience Configuration

The engine is missing `pool_pre_ping=True`, `pool_timeout`, and `pool_recycle`. After a database restart, stale connections in the pool will cause errors until they time out naturally.

**Proposed fix:**

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
)
```

---

### Positive Practices Observed

The codebase has strong foundations in several areas:

- Constant-time HMAC comparison via `hmac.compare_digest` — correct
- Parameterised ORM queries throughout — no SQL injection risk found
- Tenant isolation enforced in all read queries
- Generic error responses — no stack traces leaked via API
- Pagination limits enforced at 100 rows maximum
- Pydantic type coercion on all inputs including UUID parsing
- No `dangerouslySetInnerHTML` or `eval` anywhere in the frontend

---

## Proposed Remediation Plan

Remediation is split into three phases based on urgency.

### Phase 1 — P0 Emergency Fixes (Do Immediately, No PR Needed)

These three changes take under an hour and block all production use until done.

**1a. Fix webhook signature bypass (CRIT-003)**

In `server/app/services/webhook_service.py`:

```python
def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    if not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

**1b. Restrict CORS (CRIT-002)**

In `server/app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # e.g. ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Add `allowed_origins: list[str]` to `Settings` with a safe default.

**1c. Rotate all credentials in `server/.env`**

- GitHub App webhook secret
- Cron secret
- Any access tokens derived from the existing installation

This is operational, not a code change, but must happen before any production traffic.

---

### Phase 2 — API Authentication (Within Sprint)

Design and implement a static API key guard as a stopgap until OIDC is designed.

**Approach:** FastAPI dependency injected on all non-webhook routes, using `Authorization: Bearer` — consistent with the existing cron secret auth and standard RFC 7235 semantics:

```python
# server/app/auth.py
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings

_bearer_scheme = HTTPBearer()

async def require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=401, detail="API key not configured")
    if not hmac.compare_digest(credentials.credentials, settings.api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
```

Apply to all routers except the webhook endpoint:

```python
app.include_router(repos_router, dependencies=[Depends(require_api_key)])
```

Add `api_key: str` to `Settings`, generated on first run and stored in `.env`.

Update the frontend to pass the key via `Authorization: Bearer <key>` header.

---

### Phase 3 — Remaining Hardening (Within Month)

Ordered by severity:

| ID       | Change                                                                | Effort |
| -------- | --------------------------------------------------------------------- | ------ |
| HIGH-001 | Replace hardcoded tenant UUID literals with `settings.seed_tenant_id` | XS     |
| HIGH-002 | Fix token cache to module-level + add 60s expiry buffer               | S      |
| HIGH-003 | Add security headers middleware                                       | S      |
| HIGH-004 | Validate `html_url`/`target_url` on ingest                            | S      |
| HIGH-005 | Derive tenant from auth context in recompute endpoint                 | S      |
| MED-001  | Replace hardcoded DB URL in `alembic.ini`                             | XS     |
| MED-002  | Replace hardcoded password in `docker-compose.yml`                    | XS     |
| MED-003  | Add body size limit on webhook route                                  | S      |
| MED-004  | Add rate limiting middleware                                          | S      |
| MED-005  | Handle malformed JSON in webhook handler                              | XS     |
| MED-006  | Guard `console.error` in `ErrorBoundary.tsx`                          | XS     |
| ARCH-002 | Unify write path to use `settings.seed_tenant_id`                     | XS     |
| ARCH-005 | Add `pool_pre_ping`, `pool_recycle`, `pool_timeout` to engine         | XS     |

#### Deferred (Separate RFC Required)

| ID       | Change                                           | Reason                                      |
| -------- | ------------------------------------------------ | ------------------------------------------- |
| ARCH-001 | Full OIDC/JWT authentication design              | Requires product decisions on multi-tenancy |
| ARCH-003 | Shared Redis token cache for multi-worker safety | Requires infrastructure change              |
| ARCH-004 | Async webhook processing with retry/DLQ          | Significant architecture change             |

---

## Out of Scope

- Full multi-tenant authentication (OIDC, user management, SSO) — requires a dedicated RFC once the business model is defined.
- End-to-end encryption of stored GitHub tokens — low priority while single-tenant.
- Dependency vulnerability scanning (Dependabot/Snyk) — add as a CI step separately.

---

## Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a static API key guard to all non-webhook routes as a stopgap auth mechanism, and wire the frontend to send the key on every request.

**Architecture:** A FastAPI dependency `require_api_key` reads `Authorization: Bearer <key>` using `HTTPBearer` (consistent with the existing cron secret auth) and compares it (constant-time) against `settings.api_key`. Applied at router-include level in `main.py` for all routers except webhooks and health. The frontend reads the key from `VITE_API_KEY` env var and attaches it as `Authorization: Bearer <key>` via a central `apiFetch` wrapper that both hooks call.

**Tech Stack:** FastAPI `HTTPBearer`, `hmac.compare_digest`, pydantic-settings, Vite `import.meta.env`, MSW for client tests.

---

### File Map

| File | Action | Purpose |
|---|---|---|
| `server/app/auth.py` | Create | `require_api_key` dependency |
| `server/app/config.py` | Modify | Add `api_key: str` field |
| `server/app/main.py` | Modify | Apply auth to routers |
| `server/tests/test_auth.py` | Create | Unit tests for the dependency |
| `server/tests/conftest.py` | Modify | Override `require_api_key` in all test fixtures |
| `server/.env.example` | Modify | Document `API_KEY` setting |
| `client/src/lib/api.ts` | Create | `apiFetch` wrapper that injects `Authorization: Bearer` |
| `client/src/hooks/useDashboard.ts` | Modify | Use `apiFetch` instead of `fetch` |
| `client/src/hooks/useRepos.ts` | Modify | Use `apiFetch` instead of `fetch` |
| `client/src/hooks/useDashboard.test.ts` | Modify | Assert header is sent |
| `client/src/hooks/useRepos.test.ts` | Modify | Assert header is sent |
| `client/.env.example` | Create | Document `VITE_API_KEY` setting |

---

### Task 1: `require_api_key` dependency + Settings field

**Files:**
- Create: `server/app/auth.py`
- Modify: `server/app/config.py`
- Create: `server/tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_auth.py
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import require_api_key


def make_secured_app():
    from fastapi import Depends
    app = FastAPI()

    @app.get("/protected")
    async def protected(_: None = Depends(require_api_key)):
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_missing_auth_header_returns_403():
    """HTTPBearer returns 403 when Authorization header is absent."""
    app = make_secured_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401():
    app = make_secured_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unconfigured_api_key_returns_401():
    """When api_key is not configured the dependency must reject all requests."""
    app = make_secured_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"Authorization": "Bearer anything"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_correct_api_key_returns_200():
    from unittest.mock import patch
    app = make_secured_app()
    with patch("app.auth.settings") as mock_settings:
        mock_settings.api_key = "secret-key"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer secret-key"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd server && python -m pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Add `api_key` to Settings**

In `server/app/config.py`, add the field:

```python
api_key: str = ""
```

after `allowed_origins`.

- [ ] **Step 4: Create `server/app/auth.py`**

```python
import hmac

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer_scheme = HTTPBearer()


async def require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=401, detail="API key not configured")
    if not hmac.compare_digest(credentials.credentials, settings.api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd server && python -m pytest tests/test_auth.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add server/app/auth.py server/app/config.py server/tests/test_auth.py
git commit -m "feat: add require_api_key dependency and api_key setting"
```

---

### Task 2: Apply auth to routers and update test fixtures

**Files:**
- Modify: `server/app/main.py`
- Modify: `server/tests/conftest.py`

- [ ] **Step 1: Write a failing integration test**

Add to `server/tests/test_repos.py`:

```python
@pytest.mark.asyncio
async def test_list_repos_requires_api_key(mock_session):
    """Unauthenticated requests to protected routes must return 401."""
    from app.main import create_app
    from httpx import ASGITransport, AsyncClient
    from app.db import get_session

    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    # deliberately do NOT override require_api_key

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test"
    ) as client:
        resp = await client.get("/api/repos")

    assert resp.status_code == 403  # HTTPBearer returns 403 for missing Authorization header
```

- [ ] **Step 2: Run the new test to confirm it fails (returns 200, not 403)**

```bash
cd server && python -m pytest tests/test_repos.py::test_list_repos_requires_api_key -v
```

Expected: FAIL (asserts 403 but gets 200)

- [ ] **Step 3: Apply `require_api_key` to routers in `main.py`**

```python
# server/app/main.py  (add import)
from fastapi import Depends
from app.auth import require_api_key

# In create_app(), replace the protected router includes:
app.include_router(health.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")
app.include_router(repos.router, prefix="/api", dependencies=[Depends(require_api_key)])
app.include_router(environments.router, prefix="/api", dependencies=[Depends(require_api_key)])
app.include_router(deployments.router, prefix="/api", dependencies=[Depends(require_api_key)])
app.include_router(pull_requests.router, prefix="/api", dependencies=[Depends(require_api_key)])
app.include_router(metrics.router, prefix="/api", dependencies=[Depends(require_api_key)])
```

- [ ] **Step 4: Run new test to confirm it now passes**

```bash
cd server && python -m pytest tests/test_repos.py::test_list_repos_requires_api_key -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite — expect many 401 failures**

```bash
cd server && python -m pytest -v 2>&1 | tail -30
```

Expected: most existing tests now fail with 401

- [ ] **Step 6: Override `require_api_key` in the `client` fixture in `conftest.py`**

In `server/tests/conftest.py`, update the `client` fixture:

```python
from app.auth import require_api_key

@pytest.fixture
def client(mock_session, tenant_id):
    app = create_app()

    async def override_session():
        yield mock_session

    repo = make_repo(id=REPO_ID)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_tenant_id] = lambda: tenant_id
    app.dependency_overrides[get_verified_repo] = lambda: repo
    app.dependency_overrides[require_api_key] = lambda: None  # bypass auth in tests

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")
```

Also update the `metrics_client` fixture in `server/tests/test_metrics_routes.py`:

```python
from app.auth import require_api_key

@pytest.fixture
def metrics_client(mock_session):
    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_api_key] = lambda: None  # bypass auth in tests
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")
```

- [ ] **Step 7: Run full test suite — all should pass**

```bash
cd server && python -m pytest -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add server/app/main.py server/tests/conftest.py server/tests/test_repos.py server/tests/test_metrics_routes.py
git commit -m "feat: apply api key auth to all non-webhook routes"
```

---

### Task 3: Update server `.env.example`

**Files:**
- Modify: `server/.env.example`

- [ ] **Step 1: Add `API_KEY` to `.env.example`**

```
# API_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
```

Add this line after `# INTERNAL_CRON_SECRET=`.

- [ ] **Step 2: Commit**

```bash
git add server/.env.example
git commit -m "docs: document API_KEY setting in .env.example"
```

---

### Task 4: Client `apiFetch` wrapper

**Files:**
- Create: `client/src/lib/api.ts`
- Modify: `client/src/hooks/useDashboard.ts`
- Modify: `client/src/hooks/useRepos.ts`
- Modify: `client/src/hooks/useDashboard.test.ts`
- Modify: `client/src/hooks/useRepos.test.ts`
- Create: `client/.env.example`

- [ ] **Step 1: Write failing tests that verify the header is sent**

In `client/src/hooks/useDashboard.test.ts`, add a new test:

```typescript
it("sends Authorization header on every request", async () => {
  const headers: string[] = []
  server.use(
    http.get("/api/metrics/unified", ({ request }) => {
      headers.push(request.headers.get("Authorization") ?? "")
      return HttpResponse.json(makeDashboardResponse())
    })
  )

  const { result } = renderHook(() => useDashboard("repo-1", 30))
  await waitFor(() => expect(result.current.loading).toBe(false))

  expect(headers[0]).toMatch(/^Bearer /)
})
```

In `client/src/hooks/useRepos.test.ts`, add:

```typescript
it("sends Authorization header on every request", async () => {
  const headers: string[] = []
  server.use(
    http.get("/api/repos", ({ request }) => {
      headers.push(request.headers.get("Authorization") ?? "")
      return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 100 })
    })
  )

  const { result } = renderHook(() => useRepos())
  await waitFor(() => expect(result.current.loading).toBe(false))

  expect(headers[0]).toMatch(/^Bearer /)
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd client && source ~/.nvm/nvm.sh && nvm use && npx vitest run src/hooks/useDashboard.test.ts src/hooks/useRepos.test.ts
```

Expected: the two new header tests FAIL

- [ ] **Step 3: Create `client/src/lib/api.ts`**

```typescript
const API_KEY = import.meta.env.VITE_API_KEY ?? ""

export function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  return fetch(input, {
    ...init,
    headers: {
      ...init?.headers,
      Authorization: `Bearer ${API_KEY}`,
    },
  })
}
```

- [ ] **Step 4: Update `useDashboard.ts` to use `apiFetch`**

```typescript
import { apiFetch } from "@/lib/api"

// Inside fetchDashboard(), replace:
const res = await fetch(`/api/metrics/unified?repo_id=${repoId}&window=${daysWindow}`)
// with:
const res = await apiFetch(`/api/metrics/unified?repo_id=${repoId}&window=${daysWindow}`)
```

- [ ] **Step 5: Update `useRepos.ts` to use `apiFetch`**

```typescript
import { apiFetch } from "@/lib/api"

// Inside fetchRepos(), replace:
const res = await fetch("/api/repos?limit=100")
// with:
const res = await apiFetch("/api/repos?limit=100")
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
cd client && source ~/.nvm/nvm.sh && nvm use && npx vitest run src/hooks/useDashboard.test.ts src/hooks/useRepos.test.ts
```

Expected: all tests PASS (including the two new header tests)

- [ ] **Step 7: Create `client/.env.example`**

```
VITE_API_KEY=<paste the value from server/.env API_KEY>
```

- [ ] **Step 8: Commit**

```bash
git add client/src/lib/api.ts client/src/hooks/useDashboard.ts client/src/hooks/useRepos.ts client/src/hooks/useDashboard.test.ts client/src/hooks/useRepos.test.ts client/.env.example
git commit -m "feat: add apiFetch wrapper and wire API key header in client hooks"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run full server test suite**

```bash
cd server && python -m pytest -v
```

Expected: all tests PASS

- [ ] **Step 2: Run full client test suite**

```bash
cd client && source ~/.nvm/nvm.sh && nvm use && npx vitest run
```

Expected: all tests PASS

- [ ] **Step 3: Smoke-test the running app**

Generate a key and add it to both `.env` files:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Add `API_KEY=<value>` to `server/.env` and `VITE_API_KEY=<value>` to `client/.env`.

Start the server (`cd server && uvicorn app.main:app --reload`) and verify:

```bash
# Without key — should 401
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/repos

# With key — should 200
curl -s -o /dev/null -w "%{http_code}" -H "X-Api-Key: <value>" http://localhost:8000/api/repos

# Webhook — should still work without key
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/webhooks/github -d '{}'
```

- [ ] **Step 4: Finish the development branch**

Use `superpowers:finishing-a-development-branch` skill.
