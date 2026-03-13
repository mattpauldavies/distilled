# Dashboard UI

## 💼 Summary

Build the UI for our engineering health dashboard
Build this by replacing the placeholder application in the `/client` folder
Follow the patterns in the placeholder and utilise the existing tools (React and vite) and component library

---

## 🎯 Behaviour

- Display all available metrics in our [metrics taxonomy](../metrics.md)
- Details on how to display below
- Repo switcher as part of controls
- Provide a date range selector as part of controls
- Default window 30 days
- Window toggle: 7 / 30 / 90

---

## ❌ Explicitly Not Included

These things will be tackled later:

- Authentication
- Settings incl. user control
- Github connection setup

---

## 📊 Components

Metric Cards:

These should be big number cards that are easily grokable

- Deployment Frequency
- Lead Time
- PR Cycle Time
- Throughput
- Open PR Count

Charts:

These are beautiful interactive charts and graphs

- Deployment daily
- Lead time weekly
- Cycle time weekly
- PR ageing distribution

Data Quality:

A panel that should be less prominent that displays our trust metrics

- Attribution Coverage
- Metrics Freshness
- Setup Configuration

Notes:

- Metric widgets should have headings
- A small caption under each widget that describes what the metric is

---

## ✅ Acceptance Criteria

- Switching repo reloads metrics.
- All metrics load, cards and charts work as expected
