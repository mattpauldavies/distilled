import { afterEach, describe, expect, it, vi } from "vitest"
import { makeApiFetch } from "@/lib/api"

describe("makeApiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("attaches the Clerk token and X-Workspace-Id header", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 200 }))

    const apiFetch = makeApiFetch(
      async () => "token-123",
      () => "workspace-1"
    )
    await apiFetch("/repos")

    const [, init] = fetchSpy.mock.calls[0]
    expect(init?.headers).toMatchObject({
      Authorization: "Bearer token-123",
      "X-Workspace-Id": "workspace-1",
    })
  })

  it("omits X-Workspace-Id when no workspace getter is bound", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 200 }))

    const apiFetch = makeApiFetch(async () => "token-123")
    await apiFetch("/me/workspaces")

    const [, init] = fetchSpy.mock.calls[0]
    expect(init?.headers).not.toHaveProperty("X-Workspace-Id")
    expect(init?.headers).not.toHaveProperty("X-Tenant-Id")
  })
})
