const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

export function makeApiFetch(getToken: () => Promise<string | null>) {
  return async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
    const token = await getToken()
    return fetch(`${API_BASE}${input}`, {
      ...init,
      headers: {
        ...init?.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  }
}
