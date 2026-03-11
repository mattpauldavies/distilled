# Dashboard UI

## 💼 Summary

Single-page multi-repo engineering health dashboard.

---

## 🎯 Behaviour

- Repo switcher in header.
- Default window 30 days.
- Window toggle: 7 / 30 / 90.

---

## 🧭 Real-Time Feel

- Open PR count updates immediately after merge/close.
- Heavy metrics may lag up to 1 hour.
- Freshness timestamp visible.

---

## 📊 Components

Metric Cards:

- Deployment Frequency
- Lead Time
- PR Cycle Time
- Throughput
- Open PR Count

Charts:

- Deployment daily
- Lead time weekly
- Cycle time weekly
- PR ageing distribution

Drill-down:

- Deployment detail
- PR detail (with attribution method)

---

## ✅ Acceptance Criteria

- Switching repo reloads metrics.
- Live metrics update immediately.
- Heavy metrics reflect changes within 1 hour.
