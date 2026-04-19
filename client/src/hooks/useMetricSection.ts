import { useCallback, useEffect, useState } from "react"
import { makeApiFetch } from "@/lib/api"
import { useGetToken } from "@/lib/auth"

export interface MetricSection<T> {
  data: T | null
  loading: boolean
  error: string | null
  retry: () => void
}

export function useMetricSection<T>(
  path: string | null,
  searchParams?: Record<string, string | number>
): MetricSection<T> {
  const getToken = useGetToken()
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fetchKey, setFetchKey] = useState(0)

  const retry = useCallback(() => setFetchKey((k) => k + 1), [])

  const paramsKey = searchParams
    ? Object.entries(searchParams)
        .map(([k, v]) => `${k}=${v}`)
        .join("&")
    : ""

  useEffect(() => {
    if (!path) {
      setData(null)
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    const apiFetch = makeApiFetch(getToken)

    async function fetchSection() {
      try {
        const query = paramsKey ? `?${paramsKey}` : ""
        const res = await apiFetch(`${path}${query}`)
        if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`)
        const json: T = await res.json()
        if (!cancelled) {
          setData(json)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error")
          setData(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchSection()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, paramsKey, fetchKey])

  return { data, loading, error, retry }
}
