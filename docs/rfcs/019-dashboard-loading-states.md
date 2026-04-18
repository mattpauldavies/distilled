# RFC 019: Dashboard Loading States

**Branch:** `claude/add-dashboard-loading-states-O6xn8`

---

## Summary

Three UX issues on first-run and data-fetch flows in `/client`:

1. A blank dashboard shell renders for ~1s before we know if the tenant has repos, then flashes to the install screen.
2. All charts and metric cards share a single loading state tied to the monolithic `/metrics/unified` endpoint — one slow query blocks every tile.
3. When a tenant has installed the GitHub App and we have repos but no metrics have been computed yet, the dashboard renders fully empty with no explanation.

This RFC proposes: an app-level "initialising…" gate, per-section parallel data fetching with independent loading states, and a one-shot "data is on its way" modal for the cold-start case.

---

## Background

- `App.tsx:7` renders `<Dashboard />` immediately once Clerk reports `SignedIn`.
- `Dashboard.tsx:42` calls `useRepos()`, which starts with `loading: true`. The onboarding gate at `Dashboard.tsx:50` is `!reposLoading && !reposError && repos.length === 0` — **while `reposLoading` is true, the condition is false**, so the full dashboard frame (header, controls, 5 metric cards, 4 chart panels) renders with empty skeletons. When `/repos` resolves with zero items, the frame is thrown away and `OnboardingScreen` takes over. That is the flash.
- `useDashboard.ts:29` hits `GET /api/metrics/unified` — a single request whose `loading` flag is forwarded to every `MetricCard` (`Dashboard.tsx:128`) and `ChartPanel` (`Dashboard.tsx:173`). Fast metrics (e.g. `open_prs`, a single count query) wait for slow ones (e.g. weekly cycle-time percentiles).
- RFC 010 originally justified a unified endpoint to avoid N+1, but also noted "All queries are sequential on a single session" — so parallel per-section fetches from the client can actually be **faster** wall-clock, not slower, on a multi-worker server.
- `data_quality.freshness.last_refresh_at` is `null` on a brand-new repo until the first scheduled recompute (RFC 018) runs. That is our signal for "we have repos but no metrics yet."

---

## Design Decisions

### 1. App-level `Initialising…` gate

Hoist the `reposLoading` check out of `Dashboard.tsx` and into a new top-level branch inside `App.tsx`. Three terminal states, one loading state:

```
SignedIn
  ├── reposLoading          → <InitialisingScreen />
  ├── reposError            → <ErrorScreen />
  ├── repos.length === 0    → <OnboardingScreen />
  └── otherwise             → <Dashboard repos={repos} />
```

Why: eliminates the race entirely. `Dashboard` no longer renders while repos are unknown, so no frame can flash.

Implementation note: `useRepos` moves up one level. `Dashboard` accepts `repos` as a prop (and the `refetch` callback if we keep the polling onboarding flow, though after the gate hoist, `onReposDetected` just calls `refetch` at the parent).

`InitialisingScreen` mirrors `OnboardingScreen`'s centred layout: single "Initialising…" line, optional low-motion spinner (per CLAUDE.md "Motion: Minimal"). No brand flourish — signal over noise.

### 2. Per-section parallel fetching with independent loading

**Server side.** Split the unified endpoint into seven section endpoints that each return one unified sub-shape:

```
GET /api/metrics/deployment-frequency?repo_id=&window=
GET /api/metrics/lead-time?repo_id=&window=
GET /api/metrics/pr-cycle-time?repo_id=&window=
GET /api/metrics/throughput?repo_id=&window=
GET /api/metrics/open-prs?repo_id=
GET /api/metrics/pr-ageing?repo_id=
GET /api/metrics/data-quality?repo_id=
```

Four already exist (`deployment-frequency`, `lead-time`, `open-prs`, `pr-ageing`) but return different shapes. We change them to return the exact unified sub-shape (`DeploymentFrequencySection`, etc.) and add the three missing ones (`pr-cycle-time`, `throughput`, `data-quality`). The underlying metric service functions already exist and are what `/metrics/unified` calls today — we're just exposing them.

Delete `/metrics/unified` in the same change. We're pre-live customers — no external consumers to worry about — so there's no reason to carry a second code path. One less endpoint, one less schema, one less test file.

**Client side.** Replace `useDashboard` with seven narrow hooks, one per section, each with its own `{ data, loading, error, retry }`. They fire in parallel because `useEffect` runs are independent:

```tsx
const depFreq    = useDeploymentFrequency(repoId, daysWindow)
const leadTime   = useLeadTime(repoId, daysWindow)
const cycleTime  = usePRCycleTime(repoId, daysWindow)
const throughput = useThroughput(repoId, daysWindow)
const openPrs    = useOpenPrs(repoId)
const prAgeing   = usePRAgeing(repoId)
const freshness  = useDataQuality(repoId)
```

Each `MetricCard` / `ChartPanel` receives its own `loading` prop — the existing `Skeleton` rendering in both components already handles it. Fast tiles reveal first, slow tiles reveal when they're ready. No new UI primitives needed.

**Why not keep `/metrics/unified` and fake parallel loading in the client?** It would be dishonest — the `loading` flag would still flip to `false` for everything at the same moment. Genuinely parallel requests are the only way to get progressive reveal.

**Error handling.** Keep it per-section. A failed tile shows its existing error affordance (metric cards already degrade to `—`, chart panels have an empty state). A banner at the top appears only if every section fails, which strongly suggests an auth / network issue. This avoids a wall of red when one endpoint has a transient blip.

**Shared-query risk.** If one request authenticates differently or hits a different tenant context than another, data could mismatch. Mitigation: all seven go through the same `makeApiFetch(getToken)` and the same `require_auth` dependency, so the tenant scoping is identical to today.

### 3. "Data is on its way" modal for cold-start repos

Trigger: repos exist, dashboard data has loaded, and `data_quality.freshness.last_refresh_at === null`. This precisely identifies "repo installed, recompute has not run yet." Empty-but-refreshed repos (`last_refresh_at` set, all sections `null`) get the existing empty states — that case is normal for brand-new orgs with no PRs/deploys yet, and the modal would be noisy.

UI: shadcn `Dialog` component (add via `npx shadcn@latest add dialog`). Single short message consistent with brand voice:

> **Getting your metrics ready**
> We've found your repositories. Metrics usually appear within a few minutes of your first activity. This page will update automatically.
>
> [Got it]

Behaviour:

- Opens automatically when the trigger condition first resolves.
- Dismiss via the button or `Esc`. Once dismissed in a session, don't reappear for that repo — store dismissal in `sessionStorage` keyed by `repoId` so switching repos doesn't re-trigger for one the user has already acknowledged, but a fresh page load re-checks.
- Behind the modal: render the dashboard with its normal empty/loading states. The modal is informational, not blocking critical UI. We do **not** poll the server from the client — the scheduled recompute (RFC 018) will populate data, and users see it on next render / navigation. A follow-up could add an auto-refetch on visibility change, but that's out of scope.

---

## Component & Hook Changes

```
client/src/
├── App.tsx                            # adds Initialising/Error/Onboarding/Dashboard branch
├── components/
│   ├── InitialisingScreen.tsx         # NEW — centred "Initialising…" screen
│   ├── ReposErrorScreen.tsx           # NEW — terminal error state for /repos failure
│   ├── NoMetricsYetDialog.tsx         # NEW — cold-start informational modal
│   ├── Dashboard.tsx                  # receives repos as prop; uses per-section hooks
│   ├── MetricCard.tsx                 # unchanged (already supports `loading`)
│   ├── ChartPanel.tsx                 # unchanged (already supports `loading`)
│   └── ui/dialog.tsx                  # NEW — shadcn dialog
├── hooks/
│   ├── useRepos.ts                    # unchanged; lifted to App
│   ├── useDeploymentFrequency.ts      # NEW
│   ├── useLeadTime.ts                 # NEW
│   ├── usePRCycleTime.ts              # NEW
│   ├── useThroughput.ts               # NEW
│   ├── useOpenPrs.ts                  # NEW
│   ├── usePRAgeing.ts                 # NEW
│   ├── useDataQuality.ts              # NEW
│   └── useDashboard.ts                # DELETED (or kept as a thin fan-out wrapper during transition)
```

```
server/app/routes/metrics.py
├── /deployment-frequency              # CHANGE shape → DeploymentFrequencySection
├── /lead-time                         # CHANGE shape → LeadTimeSection
├── /pr-cycle-time                     # NEW
├── /throughput                        # NEW
├── /open-prs                          # CHANGE shape → OpenPRsSection
├── /pr-ageing                         # CHANGE shape → PRAgeingSection
├── /data-quality                      # NEW
└── /unified                           # DELETED
```

Shape-change impact: the four existing per-metric endpoints are not consumed by the current UI (which uses `/unified`). A quick `rg` confirms no client caller. Safe to change; no deprecation window needed.

---

## Testing

- **`InitialisingScreen`**: snapshot + a11y smoke (live region).
- **`App` gating**: test that `repos` loading state renders `InitialisingScreen`, error renders `ReposErrorScreen`, empty renders `OnboardingScreen`, populated renders `Dashboard`. MSW drives the states.
- **Per-section hooks**: one hook-level test each, plus a `Dashboard` integration test that uses MSW to resolve endpoints at different times and asserts that fast tiles finish their skeleton before slow ones (time-travel with `vi.useFakeTimers`).
- **`NoMetricsYetDialog`**: renders on `freshness.last_refresh_at === null`, doesn't render when set, dismiss state persists across re-renders in the same session.
- **Server**: one pytest per new/changed endpoint verifying shape parity with the `unified` section it replaces (the metric service functions are already covered).

---

## Risks & Open Questions

- **Request volume**: 7 parallel requests on every repo/window change vs 1 today. For a single tenant this is negligible; HTTP/2 multiplexing handles it. Rate limiting is per-tenant and generous. No action needed but worth flagging.
- **Perceived "flicker" of tiles appearing one-by-one**: intended. The brief states "Graphs and metrics should indicate that they are loading" — progressive reveal with skeletons satisfies this and matches Linear/Raycast feel.
- **Should the cold-start modal re-trigger on repo switch?** Proposed: yes for a repo not yet dismissed, no for one already dismissed in this session. Reasonable alternative: never auto-reopen once dismissed anywhere. Happy to defer to reviewer.

---

## Out of Scope

- Auto-polling the dashboard for new metrics after the modal appears (no server push channel yet; manual refresh is fine for v1).
- Skeleton visual redesign — current shadcn `Skeleton` is fine.
