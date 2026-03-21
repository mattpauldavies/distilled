# Client

React 19 frontend built with Vite, TypeScript, and Tailwind CSS. Pre-configured for shadcn/ui.

## Setup

```sh
nvm use        # uses .nvmrc (Node 20)
npm install
```

## Environment variables

Copy `.env.example` to `.env.local` and fill in the values:

```sh
cp .env.example .env.local
```

| Variable                    | Description                                                |
| --------------------------- | ---------------------------------------------------------- |
| `VITE_CLERK_PUBLISHABLE_KEY`| Clerk publishable key (from Clerk dashboard)               |
| `VITE_GITHUB_APP_SLUG`      | GitHub App slug for the GitHub App install URL             |

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

35 integration tests (Vitest + Testing Library + MSW) covering hooks, components, and end-to-end dashboard flows. Test infrastructure: MSW mocks HTTP, factory functions generate test data, Clerk mocked per test file.

## Lint and format

```sh
npm run lint    # ESLint + Prettier check
npm run format  # Prettier auto-fix
```

ESLint enforces TypeScript + React Hooks rules. Prettier handles code style (double quotes, semicolons, 100-char print width). `eslint-config-prettier` disables any ESLint rules that would conflict with Prettier.

## Structure

```
src/
  main.tsx                        # Entry point — wraps app in ClerkProvider
  App.tsx                         # Auth gate (SignedIn/SignedOut) + Dashboard
  index.css                       # Tailwind + theme vars
  lib/
    api.ts                        # makeApiFetch(getToken) factory
    utils.ts                      # cn() helper for shadcn
  types/dashboard.ts              # TypeScript interfaces for API responses
  hooks/
    useRepos.ts                   # Fetch repo list (Clerk-authenticated)
    useDashboard.ts               # Fetch unified dashboard metrics (Clerk-authenticated)
  components/
    SignInPage.tsx                 # Clerk sign-in page (GitHub OAuth)
    OnboardingScreen.tsx          # Guides new tenants to install the GitHub App
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
