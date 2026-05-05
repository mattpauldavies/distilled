/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useAuth } from "@clerk/clerk-react"
import { makeApiFetch } from "@/lib/api"
import type { TenantMembership } from "@/types/team"

const ACTIVE_TENANT_STORAGE_KEY = "distilled.activeTenantId"

interface TenantContextValue {
  loading: boolean
  error: string | null
  memberships: TenantMembership[]
  activeTenant: TenantMembership | null
  setActiveTenant: (tenantId: string) => void
  refresh: () => void
}

const TenantContext = createContext<TenantContextValue | null>(null)

export function TenantProvider({ children }: { children: ReactNode }) {
  const { getToken, isSignedIn } = useAuth()
  const [memberships, setMemberships] = useState<TenantMembership[]>([])
  const [activeTenantId, setActiveTenantIdState] = useState<string | null>(() => {
    if (typeof window === "undefined") return null
    return window.localStorage.getItem(ACTIVE_TENANT_STORAGE_KEY)
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), [])

  useEffect(() => {
    if (!isSignedIn) {
      setLoading(false)
      return
    }

    let cancelled = false
    const apiFetch = makeApiFetch(getToken)

    async function load() {
      setLoading(true)
      try {
        const res = await apiFetch("/me/tenants")
        if (!res.ok) throw new Error(`Failed to load tenants: ${res.status}`)
        const data: { items: TenantMembership[] } = await res.json()
        if (cancelled) return
        setMemberships(data.items)
        setError(null)

        // Resolve active tenant: stored choice if it's still a valid membership,
        // otherwise the first available membership.
        setActiveTenantIdState((current) => {
          if (current && data.items.some((m) => m.id === current)) return current
          return data.items[0]?.id ?? null
        })
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load tenants")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn, refreshKey])

  const setActiveTenant = useCallback(
    (tenantId: string) => {
      const found = memberships.find((m) => m.id === tenantId)
      if (!found) return
      setActiveTenantIdState(tenantId)
      try {
        window.localStorage.setItem(ACTIVE_TENANT_STORAGE_KEY, tenantId)
      } catch {
        // localStorage can fail in private mode; not fatal — the tab still
        // has the in-memory state and will request with X-Tenant-Id.
      }
      const apiFetch = makeApiFetch(getToken)
      apiFetch("/me/active-tenant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId }),
      }).catch(() => {
        // Best-effort; the next /me/tenants call will reconcile.
      })
    },
    [getToken, memberships]
  )

  const activeTenant = useMemo(
    () => memberships.find((m) => m.id === activeTenantId) ?? null,
    [memberships, activeTenantId]
  )

  const value = useMemo<TenantContextValue>(
    () => ({ loading, error, memberships, activeTenant, setActiveTenant, refresh }),
    [loading, error, memberships, activeTenant, setActiveTenant, refresh]
  )

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
}

export function useTenantContext(): TenantContextValue {
  const ctx = useContext(TenantContext)
  if (!ctx) {
    throw new Error("useTenantContext must be used within a <TenantProvider>")
  }
  return ctx
}

export function useActiveTenantId(): () => string | null {
  const { activeTenant } = useTenantContext()
  const ref = useRef<string | null>(activeTenant?.id ?? null)
  useEffect(() => {
    ref.current = activeTenant?.id ?? null
  }, [activeTenant])
  return useCallback(() => ref.current, [])
}

/**
 * Convenience hook: returns an apiFetch bound to the current Clerk token AND
 * the current active tenant id. Use this in data hooks that need both.
 */
export function useApiFetch(): (input: string, init?: RequestInit) => Promise<Response> {
  const { getToken } = useAuth()
  const getTenantId = useActiveTenantId()
  return useMemo(() => makeApiFetch(getToken, getTenantId), [getToken, getTenantId])
}
