import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { useApiFetch, useTenantContext } from "@/lib/tenantContext"
import type { MyInvitation } from "@/types/team"

export function InvitationBanner() {
  const apiFetch = useApiFetch()
  const { refresh, setActiveTenant } = useTenantContext()
  const [pending, setPending] = useState<MyInvitation[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    apiFetch("/me/invitations")
      .then(async (res) => {
        if (!res.ok || cancelled) return
        const data = (await res.json()) as { items: MyInvitation[] }
        if (!cancelled) setPending(data.items)
      })
      .catch(() => {
        // Banner is best-effort; never block the dashboard.
      })
    return () => {
      cancelled = true
    }
  }, [apiFetch])

  const visible = pending.filter((p) => !dismissed.has(p.id))
  if (visible.length === 0) return null

  // Show the most recent only — multiple banners would compete for attention.
  const inv = visible[0]

  async function accept() {
    setBusy(inv.id)
    try {
      const res = await apiFetch(`/me/invitations/${inv.id}/accept`, { method: "POST" })
      if (res.ok) {
        refresh() // re-fetch memberships so the new tenant appears in the switcher
        // Pre-select it locally so on next reload we land in it.
        try {
          window.localStorage.setItem("distilled.activeTenantId", inv.tenant_id)
        } catch {
          /* ignore */
        }
        setActiveTenant(inv.tenant_id)
        setDismissed((s) => new Set([...s, inv.id]))
      }
    } finally {
      setBusy(null)
    }
  }

  async function decline() {
    setBusy(inv.id)
    try {
      await apiFetch(`/me/invitations/${inv.id}/decline`, { method: "POST" })
      setDismissed((s) => new Set([...s, inv.id]))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div
      role="alert"
      className="mb-4 flex items-center justify-between gap-4 rounded-md border border-border bg-muted/40 px-4 py-3 text-sm"
    >
      <span>
        You've been invited to <strong>{inv.tenant_name}</strong>
        {inv.inviter_name ? ` by ${inv.inviter_name}` : null}.
      </span>
      <div className="flex shrink-0 gap-2">
        <Button variant="ghost" size="sm" onClick={decline} disabled={busy === inv.id}>
          Decline
        </Button>
        <Button size="sm" onClick={accept} disabled={busy === inv.id}>
          Join tenant
        </Button>
      </div>
    </div>
  )
}
