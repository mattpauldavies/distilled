# RFC 004: Client Testing

## Context

Client had no tests. Dashboard features released without coverage. Risk of regressions in metrics, filtering, error handling.

## Strategy

- **Integration-style tests** — test through rendered components (mirrors server approach)
- **Mock HTTP at boundaries** — MSW intercepts requests, no real API calls
- **Factory functions** — generate test data (makeRepo, makeDashboardResponse, etc)
- **jsdom + Happy DOM** — test DOM rendering + interactions
- **Chart components excluded** — Canvas doesn't work in jsdom (visual regression only)

## Test Infrastructure

### setup.ts

Global setup:
- MSW server with `onUnhandledRequest: 'error'` (catch unmocked requests)
- ResizeObserver polyfill (Radix UI requirement)
- afterEach cleanup

### Factories

```ts
makeRepo({ id, name, ... })
makeDashboardResponse({ deploymentChart, cycleTimeChart, ... })
makePullRequest({ ... })
```

### Custom render()

Wraps component with:
- React Router (QueryClientProvider for useQuery)
- Vitest assertions

### MSW Handlers

`handlers.ts`:
- `GET /api/repos` → list repos
- `GET /api/repos/:repo_id/dashboard` → unified endpoint

## Test Files

| File | Tests | Coverage |
|------|-------|----------|
| MetricCard.test.tsx | 3 | value/loading/setupRequired |
| ChartPanel.test.tsx | 3 | children/loading/empty |
| DataQualityPanel.test.tsx | 4 | coverage/null/freshness/production |
| DashboardControls.test.tsx | 3 | buttons/click handler/repo names |
| useRepos.test.ts | 4 | fetch/loading/error/empty |
| useDashboard.test.ts | 5 | fetch/null repoId/error/retry/repoId change |
| Dashboard.test.tsx | 5 | data rendering/loading/empty repos/errors |

## Make Commands

- `make test` — runs both server + client
- `make test-server` / `make test-client` — individual
- `make test-coverage` — both with coverage

npm equivalents in `client/`:
- `npm test` — all tests
- `npm run test:watch` — watch mode
- `npm run test:coverage` — coverage report

## Implementation

✓ vitest in vite.config.ts
✓ setup.ts with MSW + ResizeObserver
✓ Test files with 27 tests
✓ Make commands
✓ tsconfig.json updated (types: ["vitest/globals"])
✓ package.json scripts added
