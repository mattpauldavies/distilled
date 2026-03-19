import { useEffect, useState } from "react"
import type { Repo, PaginatedResponse } from "@/types/dashboard"
import { apiFetch } from "@/lib/api"

export function useRepos() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function fetchRepos() {
      try {
        const res = await apiFetch("/api/repos?limit=100")
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
  }, [])

  return { repos, loading, error }
}
