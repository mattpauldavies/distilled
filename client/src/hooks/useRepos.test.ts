import { renderHook, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { useRepos } from "./useRepos"

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: async () => "test-clerk-token" }),
}))

describe("useRepos", () => {
  it("fetches repos successfully", async () => {
    const { result } = renderHook(() => useRepos())

    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.repos).toHaveLength(2)
    expect(result.current.repos[0].full_name).toBe("org/my-repo")
    expect(result.current.error).toBeNull()
  })

  it("starts in loading state", () => {
    const { result } = renderHook(() => useRepos())
    expect(result.current.loading).toBe(true)
    expect(result.current.repos).toEqual([])
  })

  it("handles fetch error", async () => {
    server.use(
      http.get("/repos", () => {
        return new HttpResponse(null, { status: 500 })
      })
    )

    const { result } = renderHook(() => useRepos())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.error).toBe("Failed to fetch repos: 500")
    expect(result.current.repos).toEqual([])
  })

  it("handles empty repos", async () => {
    server.use(
      http.get("/repos", () => {
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 100 })
      })
    )

    const { result } = renderHook(() => useRepos())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.repos).toEqual([])
    expect(result.current.error).toBeNull()
  })

  it("sends Authorization header with Clerk token", async () => {
    const headers: string[] = []
    server.use(
      http.get("/repos", ({ request }) => {
        headers.push(request.headers.get("Authorization") ?? "")
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 100 })
      })
    )

    const { result } = renderHook(() => useRepos())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(headers[0]).toBe("Bearer test-clerk-token")
  })
})
