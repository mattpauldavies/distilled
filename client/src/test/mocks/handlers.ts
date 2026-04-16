import { http, HttpResponse } from "msw"
import { makeDashboardResponse, makeRepo } from "../factories"

export const handlers = [
  http.get("/repos", () => {
    return HttpResponse.json({
      items: [makeRepo(), makeRepo({ id: "repo-2", full_name: "org/other-repo" })],
      total: 2,
      offset: 0,
      limit: 100,
    })
  }),

  http.get("/metrics/unified", () => {
    return HttpResponse.json(makeDashboardResponse())
  }),
]
