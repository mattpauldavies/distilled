import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useApiFetch } from "@/lib/workspaceContext"
import type { AvailableRepo, WorkspaceInstallation } from "@/types/installations"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  installations: WorkspaceInstallation[]
  onAdded: () => void
}

export function AddReposModal({ open, onOpenChange, installations, onAdded }: Props) {
  const apiFetch = useApiFetch()
  const [installationId, setInstallationId] = useState<number | null>(
    installations[0]?.installation_id ?? null
  )
  const [repos, setRepos] = useState<AvailableRepo[] | null>(null)
  const [checked, setChecked] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const target = installationId ?? installations[0]?.installation_id ?? null
    if (target === null) return
    let cancelled = false
    setRepos(null)
    apiFetch(`/installations/${target}/available-repos`)
      .then(async (res) => {
        if (cancelled) return
        if (!res.ok) {
          setError(`Could not load repositories: ${res.status}`)
          return
        }
        const data = (await res.json()) as { items: AvailableRepo[] }
        setRepos(data.items)
        setError(null)
      })
      .catch(() => {
        if (!cancelled) setError("Could not load repositories")
      })
    return () => {
      cancelled = true
    }
  }, [open, installationId, installations, apiFetch])

  function toggle(githubId: number) {
    setChecked((current) => {
      const next = new Set(current)
      if (next.has(githubId)) next.delete(githubId)
      else next.add(githubId)
      return next
    })
  }

  async function addSelected() {
    const target = installationId ?? installations[0]?.installation_id
    if (!target || checked.size === 0) return
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch("/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ installation_id: target, github_ids: [...checked] }),
      })
      if (!res.ok) {
        const detail = await readDetail(res)
        setError(detail || `Could not add repositories: ${res.status}`)
        return
      }
      onAdded()
      onOpenChange(false)
      setChecked(new Set())
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
          setChecked(new Set())
          setError(null)
        }
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add repositories</DialogTitle>
          <DialogDescription>
            Pick repositories granted to your connected GitHub installations. Missing a repo? Adjust
            the installation's repository access on GitHub first.
          </DialogDescription>
        </DialogHeader>

        {installations.length > 1 ? (
          <div className="flex flex-wrap gap-2 py-1">
            {installations.map((inst) => (
              <Button
                key={inst.installation_id}
                size="sm"
                variant={
                  (installationId ?? installations[0]?.installation_id) === inst.installation_id
                    ? "default"
                    : "outline"
                }
                onClick={() => setInstallationId(inst.installation_id)}
              >
                {inst.account_login}
              </Button>
            ))}
          </div>
        ) : null}

        <div className="max-h-72 space-y-1 overflow-y-auto py-1">
          {repos === null ? (
            <p className="text-sm text-muted-foreground">Loading repositories…</p>
          ) : repos.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No repositories are granted to this installation.
            </p>
          ) : (
            repos.map((repo) => (
              <label
                key={repo.github_id}
                className="flex items-center gap-3 rounded px-2 py-1.5 text-sm hover:bg-muted"
              >
                <input
                  type="checkbox"
                  aria-label={repo.full_name}
                  disabled={repo.tracked}
                  checked={repo.tracked || checked.has(repo.github_id)}
                  onChange={() => toggle(repo.github_id)}
                  className="size-4 accent-primary"
                />
                <span className={repo.tracked ? "text-muted-foreground" : ""}>
                  {repo.full_name}
                </span>
                {repo.tracked ? (
                  <span className="ml-auto text-xs uppercase tracking-wide text-muted-foreground">
                    Added
                  </span>
                ) : null}
              </label>
            ))
          )}
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={addSelected} disabled={busy || checked.size === 0}>
            Add selected
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
