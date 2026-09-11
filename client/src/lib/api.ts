const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

export type GetToken = () => Promise<string | null>
export type GetWorkspaceId = () => string | null

export function makeApiFetch(getToken: GetToken, getWorkspaceId?: GetWorkspaceId) {
  return async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
    const token = await getToken()
    const workspaceId = getWorkspaceId?.() ?? null
    return fetch(`${API_BASE}${input}`, {
      ...init,
      headers: {
        ...init?.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
      },
    })
  }
}
