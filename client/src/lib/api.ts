const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

export type GetToken = () => Promise<string | null>
export type GetTenantId = () => string | null

export function makeApiFetch(getToken: GetToken, getTenantId?: GetTenantId) {
  return async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
    const token = await getToken()
    const tenantId = getTenantId?.() ?? null
    return fetch(`${API_BASE}${input}`, {
      ...init,
      headers: {
        ...init?.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(tenantId ? { "X-Tenant-Id": tenantId } : {}),
      },
    })
  }
}
