# Metrics Taxonomy

## Delivery Metrics

- **Deployment Frequency** — How often code ships to production. Tracks daily deployment counts to reveal release cadence and consistency.
- **Lead Time** — How long merged code waits before reaching users. Measures the gap between PR merge and production deployment (median + p75). A proxy for delivery pipeline efficiency.
- **PR Cycle Time** — How long work takes from open to merge. Measures the full review-and-iterate loop (median + p75). Highlights bottlenecks in the review process.
- **PR Throughput** — How much work the team completes per week. Weekly count of merged PRs, showing delivery volume over time.

## Work in Progress

- **Open PR Count** — How much work is in flight right now. Breaks down open PRs into live vs draft to distinguish active review from early-stage work.
- **PR Ageing** — How long open PRs have been waiting. Buckets open PRs by age (`<2d`, `2-7d`, `7-14d`, `>14d`) to surface stale work that needs attention.

## Data Quality

- **Attribution Coverage** — How complete our deploy tracking is. Percentage of merged PRs that are linked to a deployment — low coverage means lead time data is unreliable.
- **Metrics Freshness** — Whether our numbers are current. Reports `ok`, `stale`, or `no_data` based on how recently metrics were recomputed (threshold: 2 hours).
- **Setup Configuration** — Whether the pipeline is ready. Checks if a production environment is configured, which is required for deployment-based metrics.
