# RFC 011: Dashboard UI

## Summary

Build the engineering health dashboard UI in `/client`, replacing the placeholder app. Single-page React dashboard consuming the unified metrics API.

## Decisions

- **Architecture:** Single page, no routing, no state library. `useDashboard` hook + presentational components.
- **Charting:** Chart.js via react-chartjs-2
- **Component library:** shadcn/ui (Select, Card, Button, Skeleton, Badge)
- **Layout:** Stacked sections — controls → cards row → charts 2×2 grid → data quality footer
- **Window toggle:** 7/30/90 days, all server-side (add 7d support to backend)
- **Empty states:** Muted cards with setup guidance when `status: "setup_required"`
- **Custom date picker:** Deferred (API doesn't support date ranges yet)

## API

### Existing

- `GET /api/repos` — repo list for switcher
- `GET /api/metrics/unified?repo={id}&window={days}` — all dashboard data

### Changes

- Replace `DaysWindow` enum: `SEVEN=7, THIRTY=30, NINETY=90` (drops 60, adds 7). Breaking change — no existing UI consumers, safe to change.
- Propagate 7-day window through all metric service queries
- Update schema validation and any endpoint that references `DaysWindow`

## Component Tree

```
App
└── Dashboard
    ├── DashboardControls        # repo switcher + window toggle
    ├── MetricCards               # grid of big-number cards
    │   └── MetricCard ×5        # deploy freq, lead time, cycle time, throughput, open PRs
    ├── Charts                    # 2×2 grid
    │   ├── ChartPanel > DeploymentChart    # daily bar chart
    │   ├── ChartPanel > LeadTimeChart      # weekly line (median + p75)
    │   ├── ChartPanel > CycleTimeChart     # weekly line (median + p75)
    │   └── ChartPanel > PRAgeingChart      # distribution bar/doughnut
    └── DataQualityPanel          # muted footer
        ├── AttributionCoverage
        ├── MetricsFreshness
        └── SetupConfiguration
```

## Data Flow

```
DashboardControls (repoId, window)
       ↓ state lifted to Dashboard
useDashboard(repoId, window) → GET /api/metrics/unified?repo={id}&window={days}
       ↓ response
Cards, Charts, DataQuality ← presentational, receive data as props
```

## File Structure

```
src/
├── App.tsx
├── hooks/
│   ├── useDashboard.ts
│   └── useRepos.ts
├── components/
│   ├── Dashboard.tsx
│   ├── DashboardControls.tsx
│   ├── MetricCard.tsx
│   ├── ChartPanel.tsx
│   ├── DataQualityPanel.tsx
│   └── charts/
│       ├── DeploymentChart.tsx
│       ├── LeadTimeChart.tsx
│       ├── CycleTimeChart.tsx
│       └── PRAgeingChart.tsx
├── types/
│   └── dashboard.ts
├── lib/
│   └── utils.ts
└── index.css
```

## States

| State          | Behaviour                                                                                                                                                                                           |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Loading        | Skeleton placeholders in cards and chart areas                                                                                                                                                      |
| Success        | Render all data normally                                                                                                                                                                            |
| Error          | Inline error banner with retry button (manual retry only), cards/charts show "—". Covers network errors and 4xx/5xx responses.                                                                      |
| Setup required | Individual metric cards muted + "Configure production environment". Charts show a centered muted message: "No data — production environment required". Throughput, open PRs, ageing render normally |
| No repos       | Full-page empty state: "No repositories found"                                                                                                                                                      |

## Metric Cards

Each card shows: heading, big number value, small caption describing the metric. When `weekly` is null or empty, show "—" as the value.

| Card                 | Value                                                         | Caption                               |
| -------------------- | ------------------------------------------------------------- | ------------------------------------- |
| Deployment Frequency | `deployment_frequency.total`                                  | Deployments in the last {window} days |
| Lead Time            | `lead_time.weekly[-1].median_seconds` (formatted)             | Median time from merge to production  |
| PR Cycle Time        | `pr_cycle_time.weekly[-1].median_seconds` (formatted)         | Median time from PR open to merge     |
| Throughput           | `throughput.weekly[-1].pr_count`                              | PRs merged this week                  |
| Open PR Count        | `open_prs.total` with sub-label "{live} live · {draft} draft" | Currently open pull requests          |

## Charts

| Chart             | Type                 | Data                                    |
| ----------------- | -------------------- | --------------------------------------- |
| Deployment Daily  | Bar chart            | `deployment_frequency.daily_counts[]`   |
| Lead Time Weekly  | Line chart (2 lines) | `lead_time.weekly[]` — median + p75     |
| Cycle Time Weekly | Line chart (2 lines) | `pr_cycle_time.weekly[]` — median + p75 |
| PR Ageing         | Bar or doughnut      | `pr_ageing.buckets[]`                   |

## Data Quality Panel

Low-prominence section at the bottom:

- **Attribution Coverage:** percentage badge from `data_quality.attribution_coverage_percent`
- **Freshness:** status badge (ok/stale/no_data) + relative time display (e.g. "2 hours ago")
- **Setup:** green/red indicator for `has_production_environment` + comma-separated list of `production_environments` (truncate after 3 with "+N more")

## Hooks

### `useDashboard(repoId, window)`

- Returns `{ data: UnifiedDashboardResponse | null, loading: boolean, error: string | null, retry: () => void }`
- Fetches on mount and when `repoId` or `window` changes
- `retry()` re-triggers the fetch manually

### `useRepos()`

- Returns `{ repos: Repo[], loading: boolean, error: string | null }`
- Fetches `GET /api/repos` on mount
- When `repos` is empty and not loading → triggers "No repos" full-page state

## ChartPanel

Reusable wrapper providing: title, caption, loading skeleton, and empty state ("No data — production environment required" centered muted text when data is null/empty).

## shadcn/ui Components

Install: Select, Card, Button, Skeleton, Badge

## Backend Changes

- Add `7` as valid window value in the unified endpoint validation
- Propagate 7-day window through metric service queries (deployment frequency, lead time, cycle time, throughput)
