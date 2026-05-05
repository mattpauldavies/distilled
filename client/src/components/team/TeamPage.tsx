import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { InviteMemberModal } from "@/components/team/InviteMemberModal"
import { useApiFetch, useTenantContext } from "@/lib/tenantContext"
import type { Member, PendingInvitation, TeamResponse } from "@/types/team"

interface Props {
  onClose: () => void
}

export function TeamPage({ onClose }: Props) {
  const apiFetch = useApiFetch()
  const { refresh: refreshContext } = useTenantContext()

  const [team, setTeam] = useState<TeamResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState("")
  const [inviteOpen, setInviteOpen] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState<Member | null>(null)
  const [confirmTransfer, setConfirmTransfer] = useState<Member | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const reload = useCallback(async () => {
    const res = await apiFetch("/team")
    if (!res.ok) {
      setError(`Failed to load team: ${res.status}`)
      return
    }
    setTeam((await res.json()) as TeamResponse)
    setError(null)
  }, [apiFetch])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload()
  }, [reload])

  if (error) {
    return (
      <main className="mx-auto max-w-3xl space-y-6 p-6">
        <Header onClose={onClose} />
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      </main>
    )
  }
  if (!team) {
    return (
      <main className="mx-auto max-w-3xl space-y-6 p-6">
        <Header onClose={onClose} />
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    )
  }

  async function rename() {
    const cleaned = renameValue.trim()
    if (!cleaned) return
    const res = await apiFetch("/team", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: cleaned }),
    })
    if (res.ok) {
      setRenaming(false)
      reload()
      refreshContext()
    }
  }

  async function removeMember(m: Member) {
    const res = await apiFetch(`/team/members/${m.user_id}`, { method: "DELETE" })
    if (res.ok) reload()
    setConfirmRemove(null)
  }

  async function transferOwnership(m: Member) {
    const res = await apiFetch(`/team/members/${m.user_id}/transfer`, { method: "POST" })
    if (res.ok) {
      reload()
      refreshContext() // role changes — switcher needs to re-fetch
    }
    setConfirmTransfer(null)
  }

  async function revokeInvite(inv: PendingInvitation) {
    const res = await apiFetch(`/team/invitations/${inv.id}`, { method: "DELETE" })
    if (res.ok) reload()
  }

  async function resendInvite(inv: PendingInvitation) {
    const res = await apiFetch(`/team/invitations/${inv.id}/resend`, { method: "POST" })
    if (res.ok) reload()
  }

  async function deleteTenant() {
    const res = await apiFetch("/team", { method: "DELETE" })
    if (res.ok) {
      setConfirmDelete(false)
      // Drop the stored active tenant so the next mount re-resolves cleanly.
      try {
        window.localStorage.removeItem("distilled.activeTenantId")
      } catch {
        /* ignore */
      }
      window.location.replace("/")
    }
  }

  const soleUser = team.members.length === 1

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <Header onClose={onClose} />

      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="flex items-center justify-between gap-3">
            {renaming ? (
              <div className="flex flex-1 items-center gap-2">
                <Input
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  className="max-w-sm"
                  autoFocus
                />
                <Button size="sm" onClick={rename} disabled={!renameValue.trim()}>
                  Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setRenaming(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <>
                <h1 className="truncate text-xl font-semibold">{team.tenant.name}</h1>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setRenameValue(team.tenant.name)
                    setRenaming(true)
                  }}
                >
                  Rename
                </Button>
              </>
            )}
          </div>

          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Members ({team.members.length})
            </h2>
            <Button size="sm" onClick={() => setInviteOpen(true)}>
              Invite member
            </Button>
          </div>
          <ul className="divide-y divide-border">
            {team.members.map((m) => (
              <li key={m.user_id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {m.github_username ?? m.email ?? "Member"}
                  </p>
                  {m.email ? (
                    <p className="truncate text-xs text-muted-foreground">{m.email}</p>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="rounded bg-muted px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                    {m.role}
                  </span>
                  {m.role === "member" ? (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmTransfer(m)}>
                        Transfer ownership
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(m)}>
                        Remove
                      </Button>
                    </>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>

          {team.pending_invitations.length > 0 ? (
            <>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Pending invitations ({team.pending_invitations.length})
              </h2>
              <ul className="divide-y divide-border">
                {team.pending_invitations.map((inv) => (
                  <li key={inv.id} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm">{inv.email}</p>
                      <p className="text-xs text-muted-foreground">
                        Sent {timeAgo(inv.invited_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button size="sm" variant="ghost" onClick={() => resendInvite(inv)}>
                        Resend
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => revokeInvite(inv)}>
                        Revoke
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : null}

          {soleUser ? (
            <div className="border-t border-border pt-4">
              <Button
                variant="outline"
                onClick={() => setConfirmDelete(true)}
                className="text-destructive"
              >
                Delete tenant
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <InviteMemberModal
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        team={team}
        onInviteSent={() => {
          reload()
          refreshContext()
        }}
      />

      <ConfirmDialog
        open={confirmRemove !== null}
        onOpenChange={(o) => {
          if (!o) setConfirmRemove(null)
        }}
        title="Remove member?"
        description={
          confirmRemove
            ? `${confirmRemove.github_username ?? confirmRemove.email ?? "This member"} will lose access on their next interaction.`
            : ""
        }
        confirmLabel="Remove"
        destructive
        onConfirm={() => confirmRemove && removeMember(confirmRemove)}
      />

      <ConfirmDialog
        open={confirmTransfer !== null}
        onOpenChange={(o) => {
          if (!o) setConfirmTransfer(null)
        }}
        title="Transfer ownership?"
        description={
          confirmTransfer
            ? `${confirmTransfer.github_username ?? confirmTransfer.email ?? "This member"} will become owner. You'll become a regular member.`
            : ""
        }
        confirmLabel="Transfer"
        onConfirm={() => confirmTransfer && transferOwnership(confirmTransfer)}
      />

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${team.tenant.name}?`}
        description="All data in this tenant will be permanently removed. This cannot be undone."
        confirmLabel="Delete tenant"
        destructive
        onConfirm={deleteTenant}
      />
    </main>
  )
}

function Header({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <h1 className="text-xs font-semibold uppercase tracking-widest text-primary">
        Settings · Team
      </h1>
      <Button variant="ghost" size="sm" onClick={onClose}>
        Back to dashboard
      </Button>
    </div>
  )
}

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description: string
  confirmLabel: string
  destructive?: boolean
  onConfirm: () => void
}

function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 0) return "just now"
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
