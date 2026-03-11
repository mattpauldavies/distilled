# Lead Time Aggregation

## 💼 Summary

Compute lead time percentiles via scheduled job, surface attribution coverage transparently.

---

## 🎯 Scheduled Computation

For each repo:

```text
lead_time = deployed_at - pr.merged_at
```

Include only:

- PRs targeting default_branch
- PRs with valid attribution
- Positive durations

---

## 📊 Aggregates

- Weekly median
- Weekly P75
- Sample size
- Rolling coverage %

---

## 📈 Coverage Metrics (Scheduled)

- % merged PRs attributed (rolling 30d)
- Unattributed PR count
- PRs per deployment distribution

Stored in aggregate table or computed inside job and stored per repo snapshot.

---

## ❌ No Inline Recompute

No lead time recomputation during:

- Webhook ingestion
- Dashboard request

---

## ✅ Acceptance Criteria

- Lead time updates within 1 hour.
- Coverage % visible in diagnostics endpoint.
- Attribution method visible in PR detail.
