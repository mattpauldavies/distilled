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
import {
  ACTIVE_WORKSPACE_STORAGE_KEY,
  useApiFetch,
  useWorkspaceContext,
} from "@/lib/workspaceContext"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateWorkspaceModal({ open, onOpenChange }: Props) {
  const apiFetch = useApiFetch()
  const { refresh } = useWorkspaceContext()
  const [name, setName] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch("/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      })
      if (!res.ok) {
        const detail = await readDetail(res)
        setError(detail || `Could not create workspace: ${res.status}`)
        return
      }
      const data = (await res.json()) as { id: string }
      // Pre-select the new workspace; the provider resolves the stored id
      // once the refreshed membership list arrives.
      try {
        window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, data.id)
      } catch {
        /* ignore */
      }
      refresh()
      onOpenChange(false)
      setName("")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        if (!o) {
          setName("")
          setError(null)
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create a workspace</DialogTitle>
          <DialogDescription>
            A workspace has its own repositories, members, and metrics. You can move between
            workspaces from this menu.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Label htmlFor="new-workspace-name">Workspace name</Label>
          <Input
            id="new-workspace-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Engineering"
            autoFocus
          />
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={create} disabled={busy || !name.trim()}>
            Create workspace
          </Button>
        </DialogFooter>
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
