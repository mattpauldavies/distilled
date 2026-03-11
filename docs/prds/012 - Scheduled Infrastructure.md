# Scheduled Infrastructure

## 💼 Summary

Configure Railway to trigger per-repo metric recomputes hourly.

The recompute endpoint (`POST /api/internal/metrics/recompute`) and all metric logic already exist (built in PRD 005). This PRD covers only the Railway scheduling infrastructure.

---

## 🗓 Railway Scheduled Job

Fan-out: one HTTP call per repo, staggered to avoid parallel overload.

```bash
curl -X POST https://app/api/internal/metrics/recompute \
  -H "Authorization: Bearer $INTERNAL_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "...", "repo_id": "..."}'
```

---

## 🎯 Scope

- Railway job configuration (cron schedule, env vars)
- Fan-out script that queries repos and calls the endpoint per-repo with staggered timing
- Monitoring/alerting on job failures

---

## ❌ Explicitly Deferred

- Distributed job queue
- Retry backoff
- Caching layer
- Incremental percentile updates

---

## Strategic Outcome

- Heavy math runs predictably every hour
- Per-repo isolation — one repo failure doesn't block others
- Staggered timing avoids resource spikes
- No in-process scheduler
- Horizontal scaling safe
