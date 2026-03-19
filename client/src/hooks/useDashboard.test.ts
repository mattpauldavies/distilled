import { renderHook, waitFor, act } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { useDashboard } from "./useDashboard"
import { makeDashboardResponse } from "@/test/factories"

describe("useDashboard", () => {
  it("fetches dashboard data", async () => {
    const { result } = renderHook(() => useDashboard("repo-1", 30))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).not.toBeNull()
    expect(result.current.data!.deployment_frequency.total).toBe(42)
    expect(result.current.error).toBeNull()
  })

  it("returns null data when repoId is null", () => {
    const { result } = renderHook(() => useDashboard(null, 30))

    expect(result.current.data).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it("handles fetch error", async () => {
    server.use(
      http.get("/api/metrics/unified", () => {
        return new HttpResponse(null, { status: 500 })
      })
    )

    const { result } = renderHook(() => useDashboard("repo-1", 30))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.error).toBe("Failed to load metrics: 500")
    expect(result.current.data).toBeNull()
  })

  it("retries on retry()", async () => {
    let callCount = 0
    server.use(
      http.get("/api/metrics/unified", () => {
        callCount++
        if (callCount === 1) return new HttpResponse(null, { status: 500 })
        return HttpResponse.json({
          deployment_frequency: { status: "ok", total: 10, days: 30, daily_counts: [] },
          lead_time: { status: "ok", weekly: [] },
          pr_cycle_time: { status: "ok", weekly: [] },
          throughput: { weekly: [] },
          open_prs: { total: 0, live: 0, draft: 0 },
          pr_ageing: { buckets: [] },
          data_quality: {
            attribution_coverage_percent: null,
            freshness: { status: "ok", last_refresh_at: null },
            setup: { has_production_environment: false, production_environments: [] },
          },
        })
      })
    )

    const { result } = renderHook(() => useDashboard("repo-1", 30))

    await waitFor(() => expect(result.current.error).toBe("Failed to load metrics: 500"))

    act(() => result.current.retry())

    await waitFor(() => expect(result.current.data).not.toBeNull())
    expect(result.current.error).toBeNull()
  })

  it("sends Authorization header on every request", async () => {
    const headers: string[] = []
    server.use(
      http.get("/api/metrics/unified", ({ request }) => {
        headers.push(request.headers.get("Authorization") ?? "")
        return HttpResponse.json(makeDashboardResponse())
      })
    )

    const { result } = renderHook(() => useDashboard("repo-1", 30))
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(headers[0]).toMatch(/^Bearer /)
  })

  it("refetches when repoId changes", async () => {
    const urls: string[] = []
    server.use(
      http.get("/api/metrics/unified", ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json({
          deployment_frequency: { status: "ok", total: 1, days: 30, daily_counts: [] },
          lead_time: { status: "ok", weekly: [] },
          pr_cycle_time: { status: "ok", weekly: [] },
          throughput: { weekly: [] },
          open_prs: { total: 0, live: 0, draft: 0 },
          pr_ageing: { buckets: [] },
          data_quality: {
            attribution_coverage_percent: null,
            freshness: { status: "ok", last_refresh_at: null },
            setup: { has_production_environment: false, production_environments: [] },
          },
        })
      })
    )

    const { result, rerender } = renderHook(({ repoId }) => useDashboard(repoId, 30), {
      initialProps: { repoId: "repo-1" as string | null },
    })

    await waitFor(() => expect(result.current.loading).toBe(false))

    rerender({ repoId: "repo-2" })

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(urls).toHaveLength(2)
    expect(urls[0]).toContain("repo_id=repo-1")
    expect(urls[1]).toContain("repo_id=repo-2")
  })
})
