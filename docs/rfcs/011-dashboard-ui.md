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

---

# Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the engineering health dashboard UI and add 7-day window support to the backend.

**Architecture:** Single-page React dashboard with `useDashboard` hook consuming `GET /api/metrics/unified`. Stacked layout: controls, metric cards, charts (2x2), data quality footer. Backend change: add `window=7` to `DaysWindow` enum, drop 60.

**Tech Stack:** React 19, TypeScript, Tailwind 4, shadcn/ui, Chart.js (react-chartjs-2), Vite

---

## Chunk 1: Backend — 7-Day Window Support

### Task 1: Update DaysWindow enum

**Files:**
- Modify: `server/app/schemas/metrics.py:7-10`

- [ ] **Step 1: Write failing test for 7-day window**

Add to `server/tests/test_metrics_routes.py`:

```python
@pytest.mark.asyncio
async def test_unified_endpoint_accepts_7_day_window(client, mock_session):
    mock_response = UnifiedDashboardResponse(
        deployment_frequency=DeploymentFrequencySection(status="ok", total=2, days=7, daily_counts=[]),
        lead_time=LeadTimeSection(status="ok", weekly=[]),
        pr_cycle_time=PRCycleTimeSection(status="ok", weekly=[]),
        throughput=ThroughputSection(weekly=[]),
        open_prs=OpenPRsSection(total=0, live=0, draft=0),
        pr_ageing=PRAgeingSection(buckets=[]),
        data_quality=DataQuality(
            attribution_coverage_percent=None,
            freshness=FreshnessInfo(status="no_data", last_refresh_at=None),
            setup=SetupInfo(has_production_environment=True, production_environments=["production"]),
        ),
    )

    with patch("app.routes.metrics.dashboard_service.get_unified_dashboard", new_callable=AsyncMock) as mock_unified:
        mock_unified.return_value = mock_response
        resp = await client.get("/api/metrics/unified?window=7")

    assert resp.status_code == 200
    data = resp.json()
    assert data["deployment_frequency"]["days"] == 7


@pytest.mark.asyncio
async def test_unified_endpoint_rejects_60_day_window(client, mock_session):
    resp = await client.get("/api/metrics/unified?window=60")
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_metrics_routes.py::test_unified_endpoint_accepts_7_day_window tests/test_metrics_routes.py::test_unified_endpoint_rejects_60_day_window -v`

Expected: `test_unified_endpoint_accepts_7_day_window` FAIL (422 because 7 is not valid), `test_unified_endpoint_rejects_60_day_window` FAIL (200 because 60 is still valid)

- [ ] **Step 3: Update DaysWindow enum**

In `server/app/schemas/metrics.py`, replace lines 7-10:

```python
class DaysWindow(IntEnum):
    SEVEN = 7
    THIRTY = 30
    NINETY = 90
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/test_metrics_routes.py -v`

Expected: All pass including new tests. Existing `window=30` test still passes.

- [ ] **Step 5: Also run dashboard service tests**

Run: `cd server && python -m pytest tests/test_dashboard_service.py -v`

Expected: All pass (dashboard_service takes `days: int`, not `DaysWindow`, so no change needed).

- [ ] **Step 6: Commit**

```bash
git add server/app/schemas/metrics.py server/tests/test_metrics_routes.py
git commit -m "update DaysWindow enum: add 7d, drop 60d"
```

---

## Chunk 2: Frontend — Project Setup & Dependencies

### Task 2: Install dependencies

**Files:**
- Modify: `client/package.json`

- [ ] **Step 1: Install Chart.js and react-chartjs-2**

```bash
cd client && npm install chart.js react-chartjs-2
```

- [ ] **Step 2: Install shadcn/ui components**

```bash
cd client && npx shadcn@latest add select card button skeleton badge
```

- [ ] **Step 3: Verify build compiles**

```bash
cd client && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add client/
git commit -m "add chart.js, react-chartjs-2, shadcn components"
```

---

### Task 3: TypeScript types

**Files:**
- Create: `client/src/types/dashboard.ts`

- [ ] **Step 1: Create types matching API response**

Create `client/src/types/dashboard.ts`:

```typescript
export interface DailyCount {
  date: string;
  count: number;
}

export interface WeeklyPercentiles {
  week_start: string;
  median_seconds: number;
  p75_seconds: number;
  sample_size: number;
}

export interface WeeklyThroughput {
  week_start: string;
  pr_count: number;
}

export interface AgeBucket {
  bucket: string;
  count: number;
}

export interface DeploymentFrequencySection {
  status: string;
  total: number | null;
  days: number | null;
  daily_counts: DailyCount[] | null;
}

export interface LeadTimeSection {
  status: string;
  weekly: WeeklyPercentiles[] | null;
}

export interface PRCycleTimeSection {
  status: string;
  weekly: WeeklyPercentiles[] | null;
}

export interface ThroughputSection {
  weekly: WeeklyThroughput[] | null;
}

export interface OpenPRsSection {
  total: number;
  live: number;
  draft: number;
}

export interface PRAgeingSection {
  buckets: AgeBucket[];
}

export interface FreshnessInfo {
  status: string;
  last_refresh_at: string | null;
}

export interface SetupInfo {
  has_production_environment: boolean;
  production_environments: string[];
}

export interface DataQuality {
  attribution_coverage_percent: number | null;
  freshness: FreshnessInfo;
  setup: SetupInfo;
}

export interface UnifiedDashboardResponse {
  deployment_frequency: DeploymentFrequencySection;
  lead_time: LeadTimeSection;
  pr_cycle_time: PRCycleTimeSection;
  throughput: ThroughputSection;
  open_prs: OpenPRsSection;
  pr_ageing: PRAgeingSection;
  data_quality: DataQuality;
}

export interface Repo {
  id: string;
  github_id: number;
  full_name: string;
  default_branch: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export type DaysWindow = 7 | 30 | 90;
```

- [ ] **Step 2: Verify build**

```bash
cd client && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add client/src/types/dashboard.ts
git commit -m "add dashboard TypeScript types"
```

---

## Chunk 3: Frontend — Hooks

### Task 4: useRepos hook

**Files:**
- Create: `client/src/hooks/useRepos.ts`

- [ ] **Step 1: Create useRepos hook**

```typescript
import { useEffect, useState } from "react";
import type { Repo, PaginatedResponse } from "@/types/dashboard";

export function useRepos() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchRepos() {
      try {
        const res = await fetch("/api/repos?limit=100");
        if (!res.ok) throw new Error(`Failed to fetch repos: ${res.status}`);
        const data: PaginatedResponse<Repo> = await res.json();
        if (!cancelled) {
          setRepos(data.items);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchRepos();
    return () => { cancelled = true; };
  }, []);

  return { repos, loading, error };
}
```

- [ ] **Step 2: Verify build**

```bash
cd client && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add client/src/hooks/useRepos.ts
git commit -m "add useRepos hook"
```

---

### Task 5: useDashboard hook

**Files:**
- Create: `client/src/hooks/useDashboard.ts`

- [ ] **Step 1: Create useDashboard hook**

```typescript
import { useCallback, useEffect, useState } from "react";
import type { UnifiedDashboardResponse, DaysWindow } from "@/types/dashboard";

export function useDashboard(repoId: string | null, daysWindow: DaysWindow) {
  const [data, setData] = useState<UnifiedDashboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetchKey, setFetchKey] = useState(0);

  const retry = useCallback(() => setFetchKey((k) => k + 1), []);

  useEffect(() => {
    if (!repoId) {
      setData(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    async function fetchDashboard() {
      try {
        const res = await fetch(
          `/api/metrics/unified?repo=${repoId}&window=${daysWindow}`
        );
        if (!res.ok) throw new Error(`Failed to load metrics: ${res.status}`);
        const json: UnifiedDashboardResponse = await res.json();
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
          setData(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchDashboard();
    return () => { cancelled = true; };
  }, [repoId, daysWindow, fetchKey]);

  return { data, loading, error, retry };
}
```

- [ ] **Step 2: Verify build**

```bash
cd client && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add client/src/hooks/useDashboard.ts
git commit -m "add useDashboard hook"
```

---

## Chunk 4: Frontend — Controls & Metric Cards

### Task 6: DashboardControls component

**Files:**
- Create: `client/src/components/DashboardControls.tsx`

- [ ] **Step 1: Create DashboardControls**

```typescript
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import type { Repo, DaysWindow } from "@/types/dashboard";

const WINDOWS: DaysWindow[] = [7, 30, 90];

interface Props {
  repos: Repo[];
  selectedRepoId: string | null;
  onRepoChange: (repoId: string) => void;
  daysWindow: DaysWindow;
  onDaysWindowChange: (daysWindow: DaysWindow) => void;
}

export function DashboardControls({
  repos,
  selectedRepoId,
  onRepoChange,
  daysWindow,
  onDaysWindowChange,
}: Props) {
  return (
    <div className="flex items-center gap-4">
      <Select value={selectedRepoId ?? ""} onValueChange={onRepoChange}>
        <SelectTrigger className="w-[280px]">
          <SelectValue placeholder="Select a repository" />
        </SelectTrigger>
        <SelectContent>
          {repos.map((repo) => (
            <SelectItem key={repo.id} value={repo.id}>
              {repo.full_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex rounded-md border border-border">
        {WINDOWS.map((w) => (
          <Button
            key={w}
            variant={w === daysWindow ? "default" : "ghost"}
            size="sm"
            onClick={() => onDaysWindowChange(w)}
            className="rounded-none first:rounded-l-md last:rounded-r-md"
          >
            {w}d
          </Button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd client && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add client/src/components/DashboardControls.tsx
git commit -m "add DashboardControls component"
```

---

### Task 7: MetricCard component

**Files:**
- Create: `client/src/components/MetricCard.tsx`

- [ ] **Step 1: Create MetricCard**

```typescript
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  title: string;
  value: string;
  caption: string;
  subLabel?: string;
  loading?: boolean;
  setupRequired?: boolean;
}

export function MetricCard({
  title,
  value,
  caption,
  subLabel,
  loading,
  setupRequired,
}: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-20" />
        ) : setupRequired ? (
          <p className="text-sm text-muted-foreground">
            Configure a production environment to see this metric
          </p>
        ) : (
          <>
            <p className="text-3xl font-bold">{value}</p>
            {subLabel && (
              <p className="text-sm text-muted-foreground">{subLabel}</p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">{caption}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd client && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add client/src/components/MetricCard.tsx
git commit -m "add MetricCard component"
```

---

## Chunk 5: Frontend — Charts

### Task 8: ChartPanel wrapper

**Files:**
- Create: `client/src/components/ChartPanel.tsx`

- [ ] **Step 1: Create ChartPanel**

```typescript
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ReactNode } from "react";

interface Props {
  title: string;
  caption: string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
}

export function ChartPanel({ title, caption, loading, empty, emptyMessage = "No data available", children }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <p className="text-xs text-muted-foreground">{caption}</p>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-[200px] w-full" />
        ) : empty ? (
          <div className="flex h-[200px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              {emptyMessage}
            </p>
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/ChartPanel.tsx
git commit -m "add ChartPanel wrapper component"
```

---

### Task 9: DeploymentChart

**Files:**
- Create: `client/src/components/charts/DeploymentChart.tsx`

- [ ] **Step 1: Create DeploymentChart**

```typescript
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from "chart.js";
import type { DailyCount } from "@/types/dashboard";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

interface Props {
  dailyCounts: DailyCount[];
}

export function DeploymentChart({ dailyCounts }: Props) {
  const data = {
    labels: dailyCounts.map((d) => d.date),
    datasets: [
      {
        label: "Deployments",
        data: dailyCounts.map((d) => d.count),
        backgroundColor: "rgba(23, 23, 23, 0.7)",
        borderRadius: 4,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, ticks: { precision: 0 } },
      x: { ticks: { maxTicksLimit: 7 } },
    },
  };

  return (
    <div className="h-[200px]">
      <Bar data={data} options={options} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/charts/DeploymentChart.tsx
git commit -m "add DeploymentChart component"
```

---

### Task 10: LeadTimeChart

**Files:**
- Create: `client/src/components/charts/LeadTimeChart.tsx`

- [ ] **Step 1: Create LeadTimeChart**

```typescript
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import type { WeeklyPercentiles } from "@/types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

interface Props {
  weekly: WeeklyPercentiles[];
}

function toHours(seconds: number): number {
  return Math.round((seconds / 3600) * 10) / 10;
}

export function LeadTimeChart({ weekly }: Props) {
  const data = {
    labels: weekly.map((w) => w.week_start),
    datasets: [
      {
        label: "Median",
        data: weekly.map((w) => toHours(w.median_seconds)),
        borderColor: "#171717",
        backgroundColor: "rgba(23, 23, 23, 0.1)",
        tension: 0.3,
      },
      {
        label: "p75",
        data: weekly.map((w) => toHours(w.p75_seconds)),
        borderColor: "#737373",
        backgroundColor: "rgba(115, 115, 115, 0.1)",
        borderDash: [5, 5],
        tension: 0.3,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, title: { display: true, text: "Hours" } },
    },
  };

  return (
    <div className="h-[200px]">
      <Line data={data} options={options} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/charts/LeadTimeChart.tsx
git commit -m "add LeadTimeChart component"
```

---

### Task 11: CycleTimeChart

**Files:**
- Create: `client/src/components/charts/CycleTimeChart.tsx`

- [ ] **Step 1: Create CycleTimeChart**

Same structure as LeadTimeChart — intentionally separate files as they'll likely diverge.

```typescript
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import type { WeeklyPercentiles } from "@/types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

interface Props {
  weekly: WeeklyPercentiles[];
}

function toHours(seconds: number): number {
  return Math.round((seconds / 3600) * 10) / 10;
}

export function CycleTimeChart({ weekly }: Props) {
  const data = {
    labels: weekly.map((w) => w.week_start),
    datasets: [
      {
        label: "Median",
        data: weekly.map((w) => toHours(w.median_seconds)),
        borderColor: "#171717",
        backgroundColor: "rgba(23, 23, 23, 0.1)",
        tension: 0.3,
      },
      {
        label: "p75",
        data: weekly.map((w) => toHours(w.p75_seconds)),
        borderColor: "#737373",
        backgroundColor: "rgba(115, 115, 115, 0.1)",
        borderDash: [5, 5],
        tension: 0.3,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, title: { display: true, text: "Hours" } },
    },
  };

  return (
    <div className="h-[200px]">
      <Line data={data} options={options} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/charts/CycleTimeChart.tsx
git commit -m "add CycleTimeChart component"
```

---

### Task 12: PRAgeingChart

**Files:**
- Create: `client/src/components/charts/PRAgeingChart.tsx`

- [ ] **Step 1: Create PRAgeingChart**

```typescript
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from "chart.js";
import type { AgeBucket } from "@/types/dashboard";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

const BUCKET_COLORS = [
  "hsl(142, 71%, 45%)",  // <2d - green
  "hsl(48, 96%, 53%)",   // 2-7d - yellow
  "hsl(25, 95%, 53%)",   // 7-14d - orange
  "hsl(0, 84%, 60%)",    // >14d - red
];

interface Props {
  buckets: AgeBucket[];
}

export function PRAgeingChart({ buckets }: Props) {
  const data = {
    labels: buckets.map((b) => b.bucket),
    datasets: [
      {
        label: "PRs",
        data: buckets.map((b) => b.count),
        backgroundColor: buckets.map((_, i) => BUCKET_COLORS[i] ?? BUCKET_COLORS[0]),
        borderRadius: 4,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, ticks: { precision: 0 } },
    },
  };

  return (
    <div className="h-[200px]">
      <Bar data={data} options={options} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/charts/PRAgeingChart.tsx
git commit -m "add PRAgeingChart component"
```

---

## Chunk 6: Frontend — Data Quality Panel & Dashboard Assembly

### Task 13: DataQualityPanel

**Files:**
- Create: `client/src/components/DataQualityPanel.tsx`

- [ ] **Step 1: Create DataQualityPanel**

```typescript
import { Badge } from "@/components/ui/badge";
import type { DataQuality } from "@/types/dashboard";

interface Props {
  data: DataQuality;
}

function timeAgo(isoString: string | null): string {
  if (!isoString) return "Never";
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function freshnessVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "ok") return "default";
  if (status === "stale") return "secondary";
  return "destructive";
}

export function DataQualityPanel({ data }: Props) {
  const envNames = data.setup.production_environments;
  const displayEnvs =
    envNames.length <= 3
      ? envNames.join(", ")
      : `${envNames.slice(0, 3).join(", ")} +${envNames.length - 3} more`;

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <h3 className="mb-3 text-sm font-medium text-muted-foreground">
        Data Quality
      </h3>
      <div className="flex flex-wrap gap-6 text-sm">
        <div>
          <span className="text-muted-foreground">Attribution Coverage: </span>
          <Badge variant="secondary">
            {data.attribution_coverage_percent != null
              ? `${data.attribution_coverage_percent.toFixed(1)}%`
              : "N/A"}
          </Badge>
        </div>
        <div>
          <span className="text-muted-foreground">Freshness: </span>
          <Badge variant={freshnessVariant(data.freshness.status)}>
            {data.freshness.status}
          </Badge>
          <span className="ml-1 text-muted-foreground">
            {timeAgo(data.freshness.last_refresh_at)}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">Production: </span>
          {data.setup.has_production_environment ? (
            <>
              <Badge variant="default">Configured</Badge>
              {displayEnvs && (
                <span className="ml-1 text-muted-foreground">{displayEnvs}</span>
              )}
            </>
          ) : (
            <Badge variant="destructive">Not configured</Badge>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/DataQualityPanel.tsx
git commit -m "add DataQualityPanel component"
```

---

### Task 14: Dashboard orchestrator component

**Files:**
- Create: `client/src/components/Dashboard.tsx`

- [ ] **Step 1: Create Dashboard component**

This is the main orchestrator that wires everything together.

```typescript
import { useEffect, useState } from "react";
import { useRepos } from "@/hooks/useRepos";
import { useDashboard } from "@/hooks/useDashboard";
import { DashboardControls } from "@/components/DashboardControls";
import { MetricCard } from "@/components/MetricCard";
import { ChartPanel } from "@/components/ChartPanel";
import { DataQualityPanel } from "@/components/DataQualityPanel";
import { DeploymentChart } from "@/components/charts/DeploymentChart";
import { LeadTimeChart } from "@/components/charts/LeadTimeChart";
import { CycleTimeChart } from "@/components/charts/CycleTimeChart";
import { PRAgeingChart } from "@/components/charts/PRAgeingChart";
import { Button } from "@/components/ui/button";
import type { DaysWindow } from "@/types/dashboard";

function formatDuration(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round((seconds / 3600) * 10) / 10}h`;
}

export function Dashboard() {
  const { repos, loading: reposLoading, error: reposError } = useRepos();
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const [daysWindow, setDaysWindow] = useState<DaysWindow>(30);
  const { data, loading, error, retry } = useDashboard(selectedRepoId, daysWindow);

  // Auto-select first repo when loaded
  useEffect(() => {
    if (!selectedRepoId && repos.length > 0) {
      setSelectedRepoId(repos[0].id);
    }
  }, [repos, selectedRepoId]);

  // No repos state
  if (!reposLoading && !reposError && repos.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">No repositories found</p>
      </div>
    );
  }

  const depFreq = data?.deployment_frequency;
  const leadTime = data?.lead_time;
  const cycleTime = data?.pr_cycle_time;
  const throughput = data?.throughput;
  const openPrs = data?.open_prs;

  const lastLeadTime = leadTime?.weekly?.length
    ? leadTime.weekly[leadTime.weekly.length - 1]
    : null;
  const lastCycleTime = cycleTime?.weekly?.length
    ? cycleTime.weekly[cycleTime.weekly.length - 1]
    : null;
  const lastThroughput = throughput?.weekly?.length
    ? throughput.weekly[throughput.weekly.length - 1]
    : null;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <DashboardControls
          repos={repos}
          selectedRepoId={selectedRepoId}
          onRepoChange={setSelectedRepoId}
          daysWindow={daysWindow}
          onDaysWindowChange={setDaysWindow}
        />
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={retry}>
            Retry
          </Button>
        </div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-5 gap-4">
        <MetricCard
          title="Deployment Frequency"
          value={depFreq?.total != null ? String(depFreq.total) : "—"}
          caption={`Deployments in the last ${daysWindow} days`}
          loading={loading}
          setupRequired={depFreq?.status === "setup_required"}
        />
        <MetricCard
          title="Lead Time"
          value={lastLeadTime ? formatDuration(lastLeadTime.median_seconds) : "—"}
          caption="Median time from merge to production"
          loading={loading}
          setupRequired={leadTime?.status === "setup_required"}
        />
        <MetricCard
          title="PR Cycle Time"
          value={lastCycleTime ? formatDuration(lastCycleTime.median_seconds) : "—"}
          caption="Median time from PR open to merge"
          loading={loading}
          setupRequired={cycleTime?.status === "setup_required"}
        />
        <MetricCard
          title="Throughput"
          value={lastThroughput ? String(lastThroughput.pr_count) : "—"}
          caption="PRs merged this week"
          loading={loading}
        />
        <MetricCard
          title="Open PRs"
          value={openPrs ? String(openPrs.total) : "—"}
          caption="Currently open pull requests"
          subLabel={openPrs ? `${openPrs.live} live · ${openPrs.draft} draft` : undefined}
          loading={loading}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-4">
        <ChartPanel
          title="Deployments"
          caption="Daily deployment count"
          loading={loading}
          empty={depFreq?.status === "setup_required" || !depFreq?.daily_counts?.length}
          emptyMessage={depFreq?.status === "setup_required" ? "No data — production environment required" : "No deployment data"}
        >
          {depFreq?.daily_counts && <DeploymentChart dailyCounts={depFreq.daily_counts} />}
        </ChartPanel>
        <ChartPanel
          title="Lead Time"
          caption="Weekly median and p75 (hours)"
          loading={loading}
          empty={leadTime?.status === "setup_required" || !leadTime?.weekly?.length}
          emptyMessage={leadTime?.status === "setup_required" ? "No data — production environment required" : "No lead time data"}
        >
          {leadTime?.weekly && <LeadTimeChart weekly={leadTime.weekly} />}
        </ChartPanel>
        <ChartPanel
          title="PR Cycle Time"
          caption="Weekly median and p75 (hours)"
          loading={loading}
          empty={cycleTime?.status === "setup_required" || !cycleTime?.weekly?.length}
          emptyMessage={cycleTime?.status === "setup_required" ? "No data — production environment required" : "No cycle time data"}
        >
          {cycleTime?.weekly && <CycleTimeChart weekly={cycleTime.weekly} />}
        </ChartPanel>
        <ChartPanel
          title="PR Ageing"
          caption="Age distribution of open PRs"
          loading={loading}
          empty={!data?.pr_ageing?.buckets?.length}
          emptyMessage="No open PRs"
        >
          {data?.pr_ageing && <PRAgeingChart buckets={data.pr_ageing.buckets} />}
        </ChartPanel>
      </div>

      {/* Data Quality */}
      {data?.data_quality && <DataQualityPanel data={data.data_quality} />}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/Dashboard.tsx
git commit -m "add Dashboard orchestrator component"
```

---

### Task 15: Wire up App.tsx

**Files:**
- Modify: `client/src/App.tsx` (replace entirely)

- [ ] **Step 1: Replace App.tsx**

```typescript
import { Dashboard } from "@/components/Dashboard";

export default function App() {
  return <Dashboard />;
}
```

- [ ] **Step 2: Verify build**

```bash
cd client && npm run build
```

Expected: Builds with no errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/App.tsx
git commit -m "wire App.tsx to Dashboard"
```

---

## Chunk 7: Smoke Test & Documentation

### Task 16: Manual smoke test

- [ ] **Step 1: Start backend**

```bash
cd server && poetry run uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: Start frontend**

```bash
cd client && npm run dev
```

- [ ] **Step 3: Verify in browser**

Open `http://localhost:5173`. Check:
- Repo switcher loads and populates
- Window toggle switches between 7/30/90
- Metric cards show data (or setup_required state)
- Charts render correctly
- Data quality panel shows at bottom
- Switching repo reloads all metrics
- Error state appears if backend is stopped

- [ ] **Step 4: Fix any issues found**

- [ ] **Step 5: Run full backend test suite**

```bash
cd server && python -m pytest -v
```

Expected: All tests pass.

- [ ] **Step 6: Run frontend build check**

```bash
cd client && npm run build && npm run lint
```

Expected: No errors.

---

### Task 17: Update documentation

**Files:**
- Modify: `client/README.md`
- Modify: `README.md`
- Modify: `server/README.md`

- [ ] **Step 1: Update client README**

Update `client/README.md` to document:
- Dashboard component structure
- Dependencies (Chart.js, shadcn/ui components used)
- Available hooks (`useDashboard`, `useRepos`)
- How to add new metric cards or charts

- [ ] **Step 2: Update server README**

Update the API endpoints table in `server/README.md`:
- Change unified endpoint description to mention 7/30/90 day windows (was 30/60/90)

- [ ] **Step 3: Update root README**

Update `README.md` to reference the dashboard UI.

- [ ] **Step 4: Commit**

```bash
git add client/README.md server/README.md README.md
git commit -m "update docs for dashboard UI"
```
