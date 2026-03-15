# Client

React 19 frontend built with Vite, TypeScript, and Tailwind CSS. Pre-configured for shadcn/ui.

## Setup

```sh
nvm use        # uses .nvmrc (Node 20)
npm install
```

## Run

```sh
npm run dev    # http://localhost:5173
```

Vite proxies `/api` requests to `http://localhost:8000` so the backend must be running.

## Build

```sh
npm run build  # outputs to dist/
```

## Adding shadcn/ui components

`components.json` is already configured. Add components with:

```sh
npx shadcn@latest add button
npx shadcn@latest add card
```

## Test

```sh
npm test              # run all tests
npm run test:watch    # watch mode
npm run test:coverage # with coverage report
```

27 integration tests (Vitest + Testing Library + MSW) covering hooks, components, and end-to-end dashboard flows. Test infrastructure: MSW mocks HTTP, factory functions generate test data, custom render helper provides context.

## Lint

```sh
npm run lint
```

## Structure

```
src/
  main.tsx                        # Entry point
  App.tsx                         # Renders Dashboard
  index.css                       # Tailwind + theme vars
  lib/utils.ts                    # cn() helper for shadcn
  types/dashboard.ts              # TypeScript interfaces for API responses
  hooks/
    useRepos.ts                   # Fetch repo list
    useDashboard.ts               # Fetch unified dashboard metrics
  components/
    Dashboard.tsx                 # Main orchestrator — controls, cards, charts
    DashboardControls.tsx         # Repo selector + 7/30/90 day window toggle
    MetricCard.tsx                # Single metric card (loading/empty/value states)
    ChartPanel.tsx                # Chart wrapper (loading/empty/chart states)
    charts/
      DeploymentChart.tsx         # Daily deployment bar chart
      LeadTimeChart.tsx           # Weekly lead time line chart (median + p75)
      CycleTimeChart.tsx          # Weekly cycle time line chart (median + p75)
      PRAgeingChart.tsx           # Open PR age distribution bar chart
    ui/                           # shadcn components (added via CLI)
```

## Key libraries

- [Chart.js](https://www.chartjs.org/) via `react-chartjs-2` for all charts
- [shadcn/ui](https://ui.shadcn.com/) (New York style) for Card, Select, Button, Badge
