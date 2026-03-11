# Scheduled Infrastructure

## 💼 Summary

Introduce hourly scheduled recompute using Railway.

---

## 🗓 Railway Scheduled Job

Runs hourly:

```bash
curl -X POST https://app/api/internal/metrics/recompute \
  -H "Authorization: Bearer $INTERNAL_CRON_SECRET"
```

---

## 🔐 Internal Endpoint Requirements

- Must validate INTERNAL_CRON_SECRET.
- Must return non-200 on failure.
- Must log per-repo failures independently.

---

## 🧱 Idempotency Rules

- Safe to run multiple times.
- Safe under partial failure.
- No duplicate aggregate rows.

---

## ❌ Explicitly Deferred

- Distributed job queue
- Retry backoff
- Caching layer
- Incremental percentile updates

---

# Strategic Outcome

With this model:

- Heavy math runs predictably every hour.
- WIP feels real-time.
- No caching complexity.
- No in-process scheduler.
- Horizontal scaling safe.
- Correctness prioritised over premature optimisation.
