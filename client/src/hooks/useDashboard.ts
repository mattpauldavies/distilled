import { useCallback, useEffect, useState } from "react"
import type { UnifiedDashboardResponse, DaysWindow } from "@/types/dashboard"
import { makeApiFetch } from "@/lib/api"
import { useGetToken } from "@/lib/auth"

export function useDashboard(repoId: string | null, daysWindow: DaysWindow) {
  const getToken = useGetToken()
  const [data, setData] = useState<UnifiedDashboardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fetchKey, setFetchKey] = useState(0)

  const retry = useCallback(() => setFetchKey((k) => k + 1), [])

  useEffect(() => {
    if (!repoId) {
      setData(null)
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    const apiFetch = makeApiFetch(getToken)

    async function fetchDashboard() {
      try {
        const res = await apiFetch(`/api/metrics/unified?repo_id=${repoId}&window=${daysWindow}`)
        if (!res.ok) throw new Error(`Failed to load metrics: ${res.status}`)
        const json: UnifiedDashboardResponse = await res.json()
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

    fetchDashboard()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId, daysWindow, fetchKey])

  return { data, loading, error, retry }
}
