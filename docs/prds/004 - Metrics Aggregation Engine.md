# Metrics Aggregation Engine

## 💼 Summary

Introduce scheduled aggregation for heavy metrics (percentiles, time-series trends).

These metrics are recomputed hourly via Railway Scheduled Jobs.

No recompute occurs during webhook ingestion or dashboard request.

---

## 🎯 Metrics Covered (Scheduled)

- Deployment frequency (daily buckets)
- Lead time (weekly median + P75)
- PR cycle time (weekly median + P75)
- PR throughput (weekly)
- Historical lead time sample size

---

## ❌ Explicitly Not Included

- Open PR count
- PR ageing buckets (How long currently open PRs have been open, grouped by age bucket)

Those are computed on demand (see PRD 007).

---

## 🗓 Scheduled Recompute Model

Railway Scheduled Job runs hourly:

```http
POST /api/internal/metrics/recompute
Authorization: Bearer <INTERNAL_CRON_SECRET>
```

---

## 🧠 Recompute Rules

- Recompute rolling window (e.g. last 30 / 60 / 90 days).
- Use idempotent strategy:
  - DELETE + INSERT for affected ranges
    OR
  - UPSERT per bucket.

- Must be safe to run multiple times.

---

## 📦 Metric Tables

### DeploymentDailyMetric

- tenant_id
- repo_id
- date
- deployment_count
- algorithm_version

### LeadTimeWeeklyMetric

- tenant_id
- repo_id
- week_start
- median
- p75
- sample_size
- algorithm_version

### PRCycleTimeWeeklyMetric

### PRThroughputWeeklyMetric

---

## 🕒 Freshness Tracking

Add:

**MetricsRefreshLog**

- id
- tenant_id
- repo_id
- started_at
- completed_at
- status (success/failed)

Only one record per hourly run per repo.

---

## ✅ Acceptance Criteria

- Metrics update within 1 hour of new deployment/merge.
- Job is idempotent.
- Repo-level failures logged independently.
- Dashboard never queries raw event tables for heavy metrics.
