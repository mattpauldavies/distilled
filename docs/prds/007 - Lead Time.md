# Lead Time Aggregation

## Summary

Surface pre-computed lead time percentiles via a read endpoint, with inline attribution coverage.

---

## Scheduled Computation (already implemented — RFC 005)

For each repo:

```text
lead_time = deployed_at - pr.merged_at
```

Include only:

- PRs targeting default_branch
- PRs with valid attribution
- Positive durations

Weekly median, P75, and sample size already stored in `lead_time_weekly_metrics`.

---

## Read Endpoint

`GET /api/metrics/lead-time?repo_id=...&days=30`

Returns:

- Weekly buckets (median_seconds, p75_seconds, sample_size)
- `coverage_percent` — attributed PRs / total merged PRs in the window, computed on-the-fly
- Setup-aware response (like deployment-frequency)

---

## No Inline Recompute

No lead time recomputation during:

- Webhook ingestion
- Dashboard request

---

## Acceptance Criteria

- Lead time endpoint returns weekly percentiles from pre-computed data
- Coverage % included in lead-time response
- Response handles setup_required state (no production environment)
