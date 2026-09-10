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
import type { WorkspaceMembership } from "@/types/team"

export const ACTIVE_WORKSPACE_STORAGE_KEY = "distilled.activeWorkspaceId"
const LEGACY_STORAGE_KEY = "distilled.activeTenantId"

function readStoredWorkspaceId(): string | null {
  if (typeof window === "undefined") return null
  try {
    const current = window.localStorage.getItem(ACTIVE_WORKSPACE_STORAGE_KEY)
    if (current) return current
    // One-time migration from the pre-workspaces key.
    const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY)
    if (legacy) {
      window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, legacy)
      window.localStorage.removeItem(LEGACY_STORAGE_KEY)
      return legacy
    }
    return null
  } catch {
    return null
  }
}

interface WorkspaceContextValue {
  loading: boolean
  error: string | null
  memberships: WorkspaceMembership[]
  activeWorkspace: WorkspaceMembership | null
  setActiveWorkspace: (workspaceId: string) => void
  refresh: () => void
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { getToken, isSignedIn } = useAuth()
  const [memberships, setMemberships] = useState<WorkspaceMembership[]>([])
  const [activeWorkspaceId, setActiveWorkspaceIdState] = useState<string | null>(
    readStoredWorkspaceId
  )
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
        const res = await apiFetch("/me/workspaces")
        if (!res.ok) throw new Error(`Failed to load workspaces: ${res.status}`)
        const data: { items: WorkspaceMembership[] } = await res.json()
        if (cancelled) return
        setMemberships(data.items)
        setError(null)

        // Resolve active workspace: stored choice if it's still a valid
        // membership, otherwise the first available membership.
        setActiveWorkspaceIdState((current) => {
          if (current && data.items.some((m) => m.id === current)) return current
          return data.items[0]?.id ?? null
        })
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load workspaces")
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

  const setActiveWorkspace = useCallback(
    (workspaceId: string) => {
      const found = memberships.find((m) => m.id === workspaceId)
      if (!found) return
      setActiveWorkspaceIdState(workspaceId)
      try {
        window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, workspaceId)
      } catch {
        // localStorage can fail in private mode; not fatal — the tab still
        // has the in-memory state and will request with X-Workspace-Id.
      }
      const apiFetch = makeApiFetch(getToken)
      apiFetch("/me/active-workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId }),
      }).catch(() => {
        // Best-effort; the next /me/workspaces call will reconcile.
      })
    },
    [getToken, memberships]
  )

  const activeWorkspace = useMemo(
    () => memberships.find((m) => m.id === activeWorkspaceId) ?? null,
    [memberships, activeWorkspaceId]
  )

  const value = useMemo<WorkspaceContextValue>(
    () => ({ loading, error, memberships, activeWorkspace, setActiveWorkspace, refresh }),
    [loading, error, memberships, activeWorkspace, setActiveWorkspace, refresh]
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspaceContext(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) {
    throw new Error("useWorkspaceContext must be used within a <WorkspaceProvider>")
  }
  return ctx
}

export function useActiveWorkspaceId(): () => string | null {
  const { activeWorkspace } = useWorkspaceContext()
  const ref = useRef<string | null>(activeWorkspace?.id ?? null)
  useEffect(() => {
    ref.current = activeWorkspace?.id ?? null
  }, [activeWorkspace])
  return useCallback(() => ref.current, [])
}

/**
 * Convenience hook: returns an apiFetch bound to the current Clerk token AND
 * the current active workspace id. Use this in data hooks that need both.
 */
export function useApiFetch(): (input: string, init?: RequestInit) => Promise<Response> {
  const { getToken } = useAuth()
  const getWorkspaceId = useActiveWorkspaceId()
  return useMemo(() => makeApiFetch(getToken, getWorkspaceId), [getToken, getWorkspaceId])
}
