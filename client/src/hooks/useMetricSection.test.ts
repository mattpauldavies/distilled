import { act, renderHook, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { TestProviders } from "@/test/render"
import { useMetricSection } from "./useMetricSection"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token", isSignedIn: true }),
}))

describe("useMetricSection", () => {
  it("fetches and returns data", async () => {
    server.use(http.get("/metrics/foo", () => HttpResponse.json({ hello: "world" })))

    const { result } = renderHook(
      () => useMetricSection<{ hello: string }>("/metrics/foo", { repo_id: "r1" }),
      { wrapper: TestProviders }
    )

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual({ hello: "world" })
    expect(result.current.error).toBeNull()
  })

  it("does nothing when path is null", () => {
    const { result } = renderHook(() => useMetricSection("/", undefined), {
      wrapper: TestProviders,
    })
    const nullResult = renderHook(() => useMetricSection(null), { wrapper: TestProviders })
    expect(nullResult.result.current.data).toBeNull()
    expect(nullResult.result.current.loading).toBe(false)
    // the non-null one fires a real request which is fine
    expect(result.current).toBeDefined()
  })

  it("sends Authorization header", async () => {
    const seen: string[] = []
    server.use(
      http.get("/metrics/bar", ({ request }) => {
        seen.push(request.headers.get("Authorization") ?? "")
        return HttpResponse.json({})
      })
    )

    const { result } = renderHook(() => useMetricSection("/metrics/bar", { repo_id: "r1" }), {
      wrapper: TestProviders,
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(seen[0]).toBe("Bearer test-clerk-token")
  })

  it("returns error on non-2xx", async () => {
    server.use(http.get("/metrics/broken", () => new HttpResponse(null, { status: 500 })))

    const { result } = renderHook(() => useMetricSection("/metrics/broken", { repo_id: "r1" }), {
      wrapper: TestProviders,
    })
    await waitFor(() => expect(result.current.error).not.toBeNull())
    expect(result.current.error).toBe("Failed to load /metrics/broken: 500")
    expect(result.current.data).toBeNull()
  })

  it("retries on retry()", async () => {
    let calls = 0
    server.use(
      http.get("/metrics/retry", () => {
        calls++
        if (calls === 1) return new HttpResponse(null, { status: 500 })
        return HttpResponse.json({ ok: true })
      })
    )

    const { result } = renderHook(
      () => useMetricSection<{ ok: boolean }>("/metrics/retry", { repo_id: "r1" }),
      { wrapper: TestProviders }
    )
    await waitFor(() => expect(result.current.error).not.toBeNull())

    act(() => result.current.retry())

    await waitFor(() => expect(result.current.data).toEqual({ ok: true }))
    expect(result.current.error).toBeNull()
  })

  it("passes search params as querystring", async () => {
    const urls: string[] = []
    server.use(
      http.get("/metrics/windowed", ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json({})
      })
    )

    const { result } = renderHook(
      () => useMetricSection("/metrics/windowed", { repo_id: "r1", window: 90 }),
      { wrapper: TestProviders }
    )
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(urls[0]).toContain("repo_id=r1")
    expect(urls[0]).toContain("window=90")
  })

  it("refetches when a param changes", async () => {
    const urls: string[] = []
    server.use(
      http.get("/metrics/changing", ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json({})
      })
    )

    const { result, rerender } = renderHook(
      ({ repoId }: { repoId: string }) =>
        useMetricSection("/metrics/changing", { repo_id: repoId }),
      { initialProps: { repoId: "r1" }, wrapper: TestProviders }
    )
    await waitFor(() => expect(result.current.loading).toBe(false))
    rerender({ repoId: "r2" })
    await waitFor(() => expect(urls.length).toBe(2))
    expect(urls[0]).toContain("repo_id=r1")
    expect(urls[1]).toContain("repo_id=r2")
  })
})
