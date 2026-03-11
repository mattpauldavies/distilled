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

Per-repo recompute endpoint (built as part of this PRD, not PRD 012):

```http
POST /api/internal/metrics/recompute
Authorization: Bearer <INTERNAL_CRON_SECRET>
Content-Type: application/json

{ "tenant_id": "...", "repo_id": "..." }
```

Railway scheduling infrastructure (fan-out, staggering) is PRD 012's concern.

---

## 🧠 Recompute Rules

- Recompute last 90 days (covers all UI window sizes: 30/60/90).
- UPSERT per bucket (not DELETE+INSERT) — safer under partial failure.
- Must be safe to run multiple times.
- No `recompute_all` — each call targets one repo. Scheduling/fan-out across repos is deferred to PRD 012. This isolates blast radius and allows staggered recompute timing.

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

- tenant_id
- repo_id
- week_start
- median
- p75
- sample_size
- algorithm_version

### PRThroughputWeeklyMetric

- tenant_id
- repo_id
- week_start
- pr_count
- algorithm_version

---

## 🕒 Freshness Tracking

**MetricsRefreshLog**

- id
- tenant_id
- repo_id
- hour (truncated to hour — used for dedup)
- started_at
- completed_at
- status (success/failed)
- error_message
- Unique: (tenant_id, repo_id, hour)

One record per hour per repo. Retries within the same hour UPSERT the existing row.

---

## ✅ Acceptance Criteria

- Metrics update within 1 hour of new deployment/merge.
- Job is idempotent.
- Repo-level failures logged independently.
- Dashboard never queries raw event tables for heavy metrics.
