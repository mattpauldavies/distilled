# Deployment Frequency

## 💼 Summary

Expose deployment frequency derived from ProductionDeploymentEvent via scheduled aggregation.

---

## 🎯 Definition

- Count successful production deployments.
- Daily buckets.
- Summary = last N-day total.

---

## 🔁 Update Frequency

See [005-metrics-aggregation-engine.md](../rfcs/005-metrics-aggregation-engine.md) for details of aggregation

- Recomputed hourly.
- Not computed on dashboard request.

---

## 🛑 Setup States

If:

- No production environment configured → show setup required.
- No deployments detected → show zero-state guidance.

---

## ✅ Acceptance Criteria

- Reflects deploys within 1 hour.
