export function makeApiFetch(getToken: () => Promise<string | null>) {
  return async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
    const token = await getToken()
    return fetch(input, {
      ...init,
      headers: {
        ...init?.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  }
}
