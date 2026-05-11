import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useApiFetch } from "@/lib/tenantContext"
import type { TeamResponse } from "@/types/team"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  team: TeamResponse
  onInviteSent: () => void
}

type Step = "rename" | "invite"

export function InviteMemberModal({ open, onOpenChange, team, onInviteSent }: Props) {
  const apiFetch = useApiFetch()

  // Show the rename step on the first invite from a tenant whose name still
  // matches the auto-generated default and where the prompt was never
  // dismissed. The slug is set once at provisioning time from the GitHub
  // username, and the auto-name equals the slug — using slug equality is the
  // simplest robust check.
  const isDefaultName = team.tenant.slug !== null && team.tenant.name === team.tenant.slug
  const shouldShowRename = !team.rename_prompt_dismissed && isDefaultName

  const [step, setStep] = useState<Step>(shouldShowRename ? "rename" : "invite")
  const [tenantName, setTenantName] = useState(team.tenant.name)
  const [email, setEmail] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reset() {
    setStep(shouldShowRename ? "rename" : "invite")
    setTenantName(team.tenant.name)
    setEmail("")
    setError(null)
  }

  async function continueFromRename(skip: boolean) {
    setBusy(true)
    setError(null)
    try {
      const body = skip
        ? { rename_prompt_dismissed: true }
        : { name: tenantName.trim(), rename_prompt_dismissed: true }
      const res = await apiFetch("/team", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const detail = await readDetail(res)
        setError(detail || `Could not save: ${res.status}`)
        return
      }
      setStep("invite")
    } finally {
      setBusy(false)
    }
  }

  async function sendInvite() {
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch("/team/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      })
      if (!res.ok) {
        const detail = await readDetail(res)
        setError(detail || `Could not send invite: ${res.status}`)
        return
      }
      onInviteSent()
      onOpenChange(false)
      reset()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        if (!o) reset()
      }}
    >
      <DialogContent className="sm:max-w-md">
        {step === "rename" ? (
          <>
            <DialogHeader>
              <DialogTitle>Name your team</DialogTitle>
              <DialogDescription>
                You're about to invite a teammate. Give your tenant a name they'll recognise.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2 py-2">
              <Label htmlFor="tenant-name">Team name</Label>
              <Input
                id="tenant-name"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                placeholder="Acme Engineering"
                autoFocus
              />
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => continueFromRename(true)} disabled={busy}>
                Skip for now
              </Button>
              <Button
                onClick={() => continueFromRename(false)}
                disabled={busy || !tenantName.trim()}
              >
                Continue
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Invite a teammate</DialogTitle>
              <DialogDescription>
                We'll email them a link. They sign in with GitHub to accept.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2 py-2">
              <Label htmlFor="invite-email">Email address</Label>
              <Input
                id="invite-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="sam@acme.com"
                autoFocus
              />
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={sendInvite} disabled={busy || !email.trim()}>
                Send invite
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

async function readDetail(res: Response): Promise<string | null> {
  try {
    const body = await res.json()
    return typeof body?.detail === "string" ? body.detail : null
  } catch {
    return null
  }
}
