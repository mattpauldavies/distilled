import { http, HttpResponse } from "msw"
import {
  makeCycleTime,
  makeDataQuality,
  makeDeploymentFrequency,
  makeLeadTime,
  makeOpenPRs,
  makePRAgeing,
  makeRepo,
  makeThroughput,
} from "../factories"

export const handlers = [
  http.get("/me/tenants", () => {
    return HttpResponse.json({
      items: [{ id: "tenant-1", name: "Test Tenant", slug: "test", role: "owner" }],
    })
  }),

  http.get("/repos", () => {
    return HttpResponse.json({
      items: [makeRepo(), makeRepo({ id: "repo-2", full_name: "org/other-repo" })],
      total: 2,
      offset: 0,
      limit: 100,
    })
  }),

  http.get("/metrics/deployment-frequency", () => {
    return HttpResponse.json(makeDeploymentFrequency())
  }),
  http.get("/metrics/lead-time", () => {
    return HttpResponse.json(makeLeadTime())
  }),
  http.get("/metrics/pr-cycle-time", () => {
    return HttpResponse.json(makeCycleTime())
  }),
  http.get("/metrics/throughput", () => {
    return HttpResponse.json(makeThroughput())
  }),
  http.get("/metrics/open-prs", () => {
    return HttpResponse.json(makeOpenPRs())
  }),
  http.get("/metrics/pr-ageing", () => {
    return HttpResponse.json(makePRAgeing())
  }),
  http.get("/metrics/data-quality", () => {
    return HttpResponse.json(makeDataQuality())
  }),
]
