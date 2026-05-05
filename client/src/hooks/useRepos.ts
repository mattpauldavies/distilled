import { useCallback, useEffect, useState } from "react"
import type { Repo, PaginatedResponse } from "@/types/dashboard"
import { useApiFetch, useTenantContext } from "@/lib/tenantContext"

export function useRepos() {
  const apiFetch = useApiFetch()
  const { activeTenant } = useTenantContext()
  const [repos, setRepos] = useState<Repo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fetchKey, setFetchKey] = useState(0)

  const refetch = useCallback(() => setFetchKey((k) => k + 1), [])

  useEffect(() => {
    if (!activeTenant) {
      // Tenant still resolving; stay in the loading state so consumers
      // don't briefly render an empty-repos UI.
      setRepos([])
      return
    }
    let cancelled = false
    setLoading(true)

    async function fetchRepos() {
      try {
        const res = await apiFetch("/repos?limit=100")
        if (!res.ok) throw new Error(`Failed to fetch repos: ${res.status}`)
        const data: PaginatedResponse<Repo> = await res.json()
        if (!cancelled) {
          setRepos(data.items)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchRepos()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchKey, activeTenant?.id])

  return { repos, loading, error, refetch }
}
