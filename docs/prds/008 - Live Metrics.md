# Live Metrics

## 💼 Summary

Compute lightweight, “live-ish” metrics on demand at dashboard request time.

No scheduled aggregation. No caching.

---

## 🎯 Metrics (On-Demand)

### 1️⃣ Open PR Count

Query:

- PRs where `merged_at IS NULL`
- base_ref == default_branch
- Exclude draft PRs (optional)

---

### 2️⃣ PR Ageing Buckets

Computed directly via SQL:

Buckets:

- <2 days
- 2–7 days
- 7–14 days
- > 14 days

Use `NOW() - created_at`.

---

## ⚡ Performance Constraint

Queries must:

- Use proper indexes:
  - `(tenant_id, repo_id, merged_at)`
  - `(tenant_id, repo_id, created_at)`

- Execute under 100ms for typical repo size (<10k PRs).

---

## ❌ Not Included

- Percentiles
- Weekly historical trends
- Complex aggregation

---

## ✅ Acceptance Criteria

- Open PR count reflects changes immediately.
- Age buckets accurate at request time.
- Dashboard load remains performant without cache.
