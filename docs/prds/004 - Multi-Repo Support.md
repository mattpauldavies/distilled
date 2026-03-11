# Multi-Repo Support

## 💼 Summary

Support multiple repositories per tenant and introduce explicit repo context across backend.

In the future: our dashboard will always be scoped to a single active repo.

---

## 🎯 Goals

- Support multiple repos per GitHub App installation.
- Ensure all metrics are repo-scoped.
- Prepare metrics system for per-repo scheduled recompute.

---

## 🧩 Functional Scope

### Backend Repo Scoping

All metric endpoints must require:

- `tenant_id`
- `repo_id`

No cross-repo aggregation in MVP.

---

## ✅ Acceptance Criteria

- Multiple repos visible per tenant.
- No cross-repo data mixing.
