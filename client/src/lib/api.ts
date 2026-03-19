const API_KEY = import.meta.env.VITE_API_KEY ?? ""

export function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  return fetch(input, {
    ...init,
    headers: {
      ...init?.headers,
      Authorization: `Bearer ${API_KEY}`,
    },
  })
}
