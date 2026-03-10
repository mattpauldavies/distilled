# Data Quality Panel

## 💼 Summary

Expose detection health and metrics freshness.

---

## 🎯 Display (Per Repo)

- Selected production environments
- Deployments detected (30d)
- Lead time attribution coverage %
- Last metrics refresh time
- Freshness indicator:
  - If >2 hours stale → show warning

---

## 🕒 Freshness Rule

Dashboard reads:

```text
last_metrics_refresh_at = max(completed_at)
```

If:

- No record → “Metrics not computed yet”
- > 2 hours old → show stale banner

---

## ✅ Acceptance Criteria

- Users can see when data was last refreshed.
- Staleness clearly indicated.
- No silent outdated data.
