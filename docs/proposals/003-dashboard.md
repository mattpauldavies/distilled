# Dashboard API and UI

**Status:** Shipped
**Consolidates:** PRD 010 (unified dashboard API), PRD 011 (dashboard UI), RFC 010, RFC 011, RFC 013 (chart info tooltips), RFC 019 (loading states)

## Summary

The dashboard is the product. An engineering leader opens it to get an answer, not to
explore, so the whole design goal is: the key story is legible within three seconds, and
nothing on screen lies about what it knows.

## API shape

Seven endpoints, one per dashboard section, all workspace- and repo-scoped:

```
GET /metrics/deployment-frequency   ?repo_id=&window=
GET /metrics/lead-time              ?repo_id=&window=
GET /metrics/pr-cycle-time          ?repo_id=&window=
GET /metrics/throughput             ?repo_id=&window=
GET /metrics/data-quality           ?repo_id=&window=
GET /metrics/open-prs               ?repo_id=
GET /metrics/pr-ageing              ?repo_id=
```

`window` is 30, 90, or 180 days, defaulting to 30.

This replaced a single `GET /metrics/unified` endpoint, which was deleted rather than kept
alongside — see the decision below. Each endpoint delegates to one section builder in
`read_metrics_service`, so a metric's full read path lives in one module.

Sections that depend on deployments return `status: "setup_required"` with null data when no
production environment is configured. Throughput, open PRs, and ageing always return data.

## UI

A single page, no routing library for the dashboard itself, no state library. One hook per
section, each returning `{ data, loading, error, retry }`; `Dashboard.tsx` calls each hook
exactly once and passes the result down to purely presentational components.

**Controls** — workspace-aware repo switcher and a window toggle.

**Metric cards** — deployment frequency, lead time, PR cycle time, throughput, open PR
count. Each is a heading, one large number, and a one-line caption saying what the metric
is. Missing data renders as `—`, never as zero.

**Charts** — deployment daily (bar), lead time weekly and cycle time weekly (line, median
and P75), PR ageing distribution. Each chart panel carries an `(i)` button in its header
opening a popover that explains what the chart shows and how to read it. Click to open,
click outside or Escape to dismiss — a deliberate interaction, not a hover.

**Data quality panel** — attribution coverage, freshness, and setup configuration, styled
to recede. These are trust signals, not headline metrics.

### States

| State           | Behaviour                                                                 |
| --------------- | -------------------------------------------------------------------------- |
| Initialising    | App-level gate while the repo list is unknown — no dashboard frame renders   |
| Loading         | Per-section skeletons; fast tiles reveal before slow ones                   |
| Success         | Normal render                                                               |
| Section error   | That card or panel shows "Failed to load" with a retry; a banner appears only if every section fails |
| Setup required  | Affected cards muted with setup guidance; unaffected sections render normally |
| No repos        | Onboarding screen                                                           |
| No metrics yet  | Dashboard renders with empty states, plus a one-shot dialog explaining that metrics are on their way |

## Decisions

**Per-section endpoints, and delete `/metrics/unified`.** The unified endpoint ran its
queries sequentially on one session and returned one `loading` flag, so a single slow
percentile query blocked every tile — including an open-PR count that is one `COUNT(*)`.
Faking per-tile loading on top of it would have been dishonest, because the flag still
flips for everything at the same moment. Parallel requests are the only way to get genuine
progressive reveal. Keeping both endpoints would have meant two code paths and two schemas
for one screen, and there were no external consumers, so the old one went.

**Errors are per-section.** One transient blip should not paint the screen red. A banner
appears only when every section fails, which points at auth or network rather than a
metric.

**Chart panels must have an error state.** Before this, a failed request rendered "No lead
time data for this period" — factually wrong, and exactly the kind of quiet lie that
destroys trust in a metrics product.

**App-level initialising gate.** The dashboard frame used to render while the repo list was
still loading, then be thrown away when the list came back empty — a visible flash into the
install screen. Hoisting `useRepos` into `App` and branching there removes the race rather
than papering over it.

**The cold-start dialog triggers on `last_refresh_at === null` only.** That precisely means
"repos connected, recompute has not run yet". A repo that has been refreshed but has no
activity gets the ordinary empty states — showing the dialog there would be noise.
Dismissal is stored in `localStorage` per repo.

**Chart.js via react-chartjs-2, shadcn/ui, Chart.js canvas excluded from unit tests.**
Canvas does not work under jsdom, so charts are covered by the Playwright smoke suite
instead of unit tests.

**No custom date-range picker.** The API takes a window, not a range. Adding a picker would
mean inventing an API contract the backend does not have.

## History

- **PRD 010 / RFC 010** built `GET /metrics/unified` and moved query functions out of route
  handlers into domain services, with `dashboard_service` as a thin orchestrator.
- **PRD 011 / RFC 011** replaced the placeholder client with the dashboard.
- **RFC 013** added the chart info popovers.
- **RFC 019** split the unified endpoint into seven, deleted it, added the app-level
  initialising gate and the cold-start dialog.
- **RFC 022** removed duplicate fetches (each windowed metric was being requested twice),
  gave chart panels an error state, and merged the byte-identical lead-time and cycle-time
  chart components into one — see [008 Engineering Practice](008-engineering-practice.md).
- The window options were 30/60/90 in RFC 010, 7/30/90 in RFC 011, and are now **30/90/180**.
