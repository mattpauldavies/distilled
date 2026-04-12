# RFC 017 — Server Security Audit

**Date:** 2026-04-12
**Status:** Complete
**Scope:** Full security audit of `/server` — auth, routes, services, models, middleware, DB, scripts

---

## Executive Summary

A comprehensive security audit was performed across all major server files (50+ source files). **21 unique findings** were identified: **3 Critical**, **6 High**, **8 Medium**, and **4 Low**. No SQL injection vulnerabilities were found — the codebase consistently uses SQLAlchemy ORM with parameterized queries. The most significant issues center on JWT validation gaps, tenant isolation inconsistencies, and missing production hardening.

---

## Findings

### CRITICAL

#### C-1: JWT Audience (`aud`) Verification Disabled

- **File:** `app/services/clerk_service.py:71`
- **Code:** `options={"verify_aud": False}`
- **Impact:** Any valid Clerk JWT issued for a *different* application sharing the same Clerk instance is accepted. An attacker with a JWT from another Clerk-integrated app can authenticate to this API.
- **Fix:** Enable audience verification and configure the expected audience:
  ```python
  claims = jwt.decode(token, key, algorithms=["RS256"],
                      audience=settings.clerk_expected_audience)
  ```

#### C-2: JWT Issuer (`iss`) Not Validated

- **File:** `app/services/clerk_service.py:67-72`
- **Impact:** Combined with C-1, any JWT signed by any key in the JWKS endpoint is accepted regardless of who issued it. This widens the token confusion attack surface.
- **Fix:** Add `issuer=settings.clerk_issuer` to the `jwt.decode()` call.

#### C-3: Hardcoded Database Credentials in Config and alembic.ini

- **Files:** `app/config.py:10`, `alembic.ini:90`
- **Code:** `database_url: str = "postgresql+asyncpg://distilled:distilled@localhost:5432/distilled"`
- **Impact:** If `DATABASE_URL` env var is unset (misconfigured deploy), the app silently connects with default credentials. The same credentials are committed to version control in `alembic.ini`.
- **Fix:** Remove default values. Make `database_url` a required field with no fallback so the app refuses to start without explicit configuration.

---

### HIGH

#### H-1: Empty Security Secrets Accepted Without Startup Validation

- **File:** `app/config.py:13,16,20`
- **Code:** `github_webhook_secret: str = ""`, `internal_cron_secret: str = ""`, `clerk_secret_key: str = ""`
- **Impact:** The application starts successfully without any authentication infrastructure configured. Individual endpoints check for empty secrets, but a new endpoint could easily forget. The app should fail hard at startup in production if secrets are missing.
- **Fix:** Add a `@model_validator` to `Settings` that raises `RuntimeError` if critical secrets are empty when `environment == "production"`.

#### H-2: IDOR — Missing `tenant_id` Filter on Cross-Table Joins in Detail Endpoints

- **Files:** `app/routes/deployments.py:76-80`, `app/routes/pull_requests.py:76-82`
- **Impact:** The deployment detail endpoint fetches attributed PRs without a `tenant_id` filter on the `PullRequest` table. The PR detail endpoint fetches linked deployments without a `tenant_id` filter on `ProductionDeploymentEvent`. If data integrity is compromised, cross-tenant data could leak through these joins.
- **Fix:** Add `PullRequest.tenant_id == tenant_id` and `ProductionDeploymentEvent.tenant_id == tenant_id` to the respective queries.

#### H-3: Race Condition in User/Tenant Creation (TOCTOU)

- **File:** `app/services/user_service.py:55-107`
- **Impact:** Two concurrent requests for the same `clerk_user_id` can both pass the `user is not None` check and create duplicate tenants and users, splitting data across two tenants.
- **Fix:** Use `SELECT ... FOR UPDATE` or wrap creation in a `try/except IntegrityError` with re-query on conflict.

#### H-4: Attribution Service Missing Tenant Isolation

- **File:** `app/services/attribution_service.py:22-46`
- **Impact:** Queries for previous deployments and eligible PRs filter by `repo_id` only, without `tenant_id`. Defense-in-depth gap — if a repo existed in two tenants, data would leak.
- **Fix:** Add `tenant_id` filters: `ProductionDeploymentEvent.tenant_id == deployment.tenant_id` and `PullRequest.tenant_id == deployment.tenant_id`.

#### H-5: Recompute Endpoint Accepts Arbitrary `tenant_id` from Request Body

- **File:** `app/routes/metrics.py:43-66`
- **Impact:** The `/api/metrics/recompute` endpoint authenticates via a shared static bearer token, but `tenant_id` is supplied by the caller. Anyone with the cron secret can trigger recomputation for any tenant.
- **Fix:** Validate the `(tenant_id, repo_id)` pair exists. Document that the cron secret has tenant-spanning privileges. Consider per-tenant auth.

#### H-6: No SSL/TLS Enforcement on Database Connection

- **File:** `app/db.py:8-14`
- **Impact:** No `connect_args` specify SSL. In cloud environments where the database is on a separate host, queries and credentials travel in plaintext.
- **Fix:** Enforce SSL in production via `connect_args={"ssl": ssl.create_default_context()}` or require `?sslmode=require` in the database URL.

---

### MEDIUM

#### M-1: Rate Limiter Configured But Never Applied to Any Route

- **File:** `app/main.py:24`
- **Impact:** A `slowapi` limiter is instantiated with `default_limits=["200/minute"]` but no route uses `@limiter.limit()`. The `default_limits` parameter only applies to decorated routes — there is effectively **zero rate limiting** on any endpoint.
- **Fix:** Apply `@limiter.limit()` decorators to sensitive endpoints (webhooks, recompute, auth). Or use `application_limits` for a global baseline.

#### M-2: Webhook Body Fully Read Before Size Check (Memory Exhaustion DoS)

- **File:** `app/routes/webhooks.py:34-37`
- **Impact:** The entire request body is buffered into memory *before* the 25MB size check. An attacker can send massive payloads to exhaust server memory. The endpoint is unauthenticated (signature check comes after body read).
- **Fix:** Check `Content-Length` header before reading, and/or configure a body size limit at the ASGI/reverse-proxy layer.

#### M-3: Overly Permissive CORS — Wildcard Methods and Headers

- **File:** `app/main.py:45-51`
- **Impact:** `allow_methods=["*"]` and `allow_headers=["*"]` with `allow_credentials=True` is unnecessarily broad. Allows all HTTP methods including `TRACE`, `DELETE`, `PATCH` from allowed origins.
- **Fix:** Restrict to only needed methods and headers:
  ```python
  allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
  allow_headers=["Authorization", "Content-Type"],
  ```

#### M-4: OpenAPI/Swagger Documentation Exposed in Production

- **File:** `app/main.py:36`
- **Impact:** `/docs`, `/redoc`, `/openapi.json` expose the complete API schema to unauthenticated users, aiding reconnaissance.
- **Fix:** Disable in production: `docs_url=None if settings.environment == "production" else "/docs"`.

#### M-5: Missing Security Headers (HSTS, CSP, Permissions-Policy)

- **File:** `app/main.py:54-59`
- **Impact:** No `Strict-Transport-Security` leaves users vulnerable to SSL stripping. No `Content-Security-Policy` or `Permissions-Policy`.
- **Fix:** Add `Strict-Transport-Security: max-age=31536000; includeSubDomains` in production, plus `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`.

#### M-6: JWT Error Messages Leak Internal Token Details

- **File:** `app/services/clerk_service.py:79`
- **Code:** `detail=f"Invalid token: {exc}"`
- **Impact:** PyJWT exception messages can reveal expected token structure, claim values, or algorithm info, aiding token crafting.
- **Fix:** Return generic `"Invalid token"` to client; log details server-side.

#### M-7: Seed/Reset Scripts Have No Production Guard

- **Files:** `scripts/seed_demo.py`, `scripts/reset_demo.py`
- **Impact:** Scripts connect to whatever `DATABASE_URL` is configured. If accidentally run against production, `seed_demo.py` inserts fake data and `reset_demo.py` deletes data.
- **Fix:** Add `if settings.environment == "production": sys.exit("Refusing to run against production")` at script entry.

#### M-8: Webhook Body Parsed Twice (Fragile Integrity Pattern)

- **File:** `app/routes/webhooks.py:34,47`
- **Impact:** Body is read as raw bytes for HMAC, then re-parsed via `request.json()`. While Starlette caches the body, mixing raw and parsed access is fragile — if JSON parsing normalizes data differently from the raw bytes, HMAC could validate a different payload than what's processed.
- **Fix:** Use `json.loads(body)` instead of `request.json()` to parse from the already-read bytes.

---

### LOW

#### L-1: Auth Returns 403 Instead of 401 for Missing Credentials

- **File:** `app/auth.py:28`
- **Impact:** Violates RFC 7235. Can confuse client-side token refresh flows that look for 401.
- **Fix:** Change to `status_code=401`.

#### L-2: No JWKS Cache Refresh on Key Rotation (`kid` Miss)

- **File:** `app/services/clerk_service.py:57-65`
- **Impact:** If Clerk rotates signing keys, valid tokens signed with the new key are rejected for up to 1 hour (cache TTL). No forced refresh is attempted on `kid` miss.
- **Fix:** On `kid` miss, clear cache and re-fetch JWKS once before failing.

#### L-3: GitHub URL Validation Too Permissive

- **File:** `app/services/deployment_service.py:176-179`
- **Impact:** Only checks `https://github.com/` prefix. URLs like `https://github.com/<script>` would pass, risking stored XSS if the frontend doesn't escape.
- **Fix:** Use a stricter regex: `^https://github\.com/[\w\-\.]+/[\w\-\.]+`.

#### L-4: Unbounded GitHub Repository Pagination

- **File:** `app/services/github_client.py:60-74`
- **Impact:** No upper bound on pagination loop. If `total_count` is very large, the loop consumes unbounded memory and API quota.
- **Fix:** Add `MAX_REPOS = 10_000` safeguard.

---

## Positive Findings

The audit also identified several well-implemented security patterns:

- **No SQL injection:** All queries use SQLAlchemy ORM with parameterized filters. `sa.text()` calls use hardcoded literals only.
- **Webhook HMAC verification** is correct: uses `hmac.compare_digest` for constant-time comparison, validates `sha256=` prefix, rejects empty secrets.
- **Pagination bounds** are enforced: `1 <= limit <= 100`, `offset >= 0`.
- **Tenant isolation** is generally sound on list endpoints: `tenant_id` derived from JWT, scoped in queries, verified via `get_verified_repo` middleware.
- **Health endpoint** exposes no sensitive data.
- **Environment update schema** prevents mass assignment (only `is_production: bool` accepted).

---

## Priority Remediation Order

### Immediate (this sprint)

| # | Finding | Effort |
|---|---------|--------|
| 1 | C-1, C-2: Enable JWT audience + issuer verification | Small |
| 2 | C-3: Remove hardcoded DB credentials | Small |
| 3 | H-1: Startup validation for required secrets | Small |
| 4 | H-2: Add `tenant_id` to cross-table joins | Small |
| 5 | H-3: Fix TOCTOU race in user creation | Medium |

### Next sprint

| # | Finding | Effort |
|---|---------|--------|
| 6 | H-4: Add tenant_id to attribution queries | Small |
| 7 | H-6: Enforce DB SSL in production | Small |
| 8 | M-1: Apply rate limiting decorators | Small |
| 9 | M-2: Pre-check Content-Length on webhooks | Small |
| 10 | M-6: Sanitize JWT error messages | Small |
| 11 | M-4: Disable OpenAPI in production | Small |
| 12 | M-5: Add missing security headers | Small |

### Backlog

| # | Finding | Effort |
|---|---------|--------|
| 13 | H-5: Document/restrict recompute tenant scope | Small |
| 14 | M-3: Restrict CORS methods/headers | Small |
| 15 | M-7: Add production guards to scripts | Small |
| 16 | M-8: Parse webhook body from bytes | Small |
| 17 | L-1 through L-4 | Small each |

---

## Summary Table

| Severity | Count |
|----------|-------|
| Critical | 3 |
| High | 6 |
| Medium | 8 |
| Low | 4 |
| **Total** | **21** |
