# Unified Dashboard API

## 💼 Summary

Single endpoint powering dashboard view.

---

## 🎯 Endpoint

```http
GET /api/metrics/unified?repo={id}&window=30d
```

---

## 📦 Returns

### Scheduled Metrics

- Deployment frequency summary + time series
- Lead time median + P75
- PR cycle time median + P75
- Throughput weekly

### Live Metrics

- Open PR count
- PR ageing buckets

### Data Quality

- Attribution coverage
- Last metrics refresh
- Setup flags

---

## 🧠 Data Sources

- Heavy metrics → aggregate tables
- Live metrics → direct PR queries

---

## ❌ No Caching (MVP)

Every request:

- Reads aggregate tables
- Executes live PR queries

---

## ✅ Acceptance Criteria

- Single request loads full dashboard.
- Response time acceptable (<400ms target).
- Repo-scoped.
