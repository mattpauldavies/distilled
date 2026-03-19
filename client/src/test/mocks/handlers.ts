import { http, HttpResponse } from 'msw'
import { makeDashboardResponse, makeRepo } from '../factories'

export const handlers = [
  http.get('/api/repos', () => {
    return HttpResponse.json({
      items: [makeRepo(), makeRepo({ id: 'repo-2', full_name: 'org/other-repo' })],
      total: 2,
      offset: 0,
      limit: 100,
    })
  }),

  http.get('/api/metrics/unified', () => {
    return HttpResponse.json(makeDashboardResponse())
  }),
]
