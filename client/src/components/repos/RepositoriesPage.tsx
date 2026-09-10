import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { AddReposModal } from "@/components/repos/AddReposModal"
import { useApiFetch } from "@/lib/workspaceContext"
import type { Repo, PaginatedResponse } from "@/types/dashboard"
import type { WorkspaceInstallation } from "@/types/installations"

interface Props {
  onClose: () => void
}

export function RepositoriesPage({ onClose }: Props) {
  const apiFetch = useApiFetch()

  const [repos, setRepos] = useState<Repo[] | null>(null)
  const [installations, setInstallations] = useState<WorkspaceInstallation[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState<Repo | null>(null)
  const [confirmUnlink, setConfirmUnlink] = useState<WorkspaceInstallation | null>(null)
  const [connecting, setConnecting] = useState(false)

  const reload = useCallback(async () => {
    try {
      const [reposRes, installationsRes] = await Promise.all([
        apiFetch("/repos?limit=100"),
        apiFetch("/installations"),
      ])
      if (!reposRes.ok || !installationsRes.ok) {
        setError("Failed to load repositories")
        return
      }
      const reposData = (await reposRes.json()) as PaginatedResponse<Repo>
      const installationsData = (await installationsRes.json()) as {
        items: WorkspaceInstallation[]
      }
      setRepos(reposData.items)
      setInstallations(installationsData.items)
      setError(null)
    } catch {
      setError("Failed to load repositories")
    }
  }, [apiFetch])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload()
  }, [reload])

  async function removeRepo(repo: Repo) {
    const res = await apiFetch(`/repos/${repo.id}`, { method: "DELETE" })
    if (res.ok) reload()
    setConfirmRemove(null)
  }

  async function unlinkInstallation(installation: WorkspaceInstallation) {
    const res = await apiFetch(`/installations/${installation.installation_id}`, {
      method: "DELETE",
    })
    if (res.ok) reload()
    setConfirmUnlink(null)
  }

  async function connectGitHub() {
    setConnecting(true)
    try {
      const res = await apiFetch("/installations/intents", { method: "POST" })
      if (!res.ok) {
        setError(`Could not prepare the GitHub connection: ${res.status}`)
        return
      }
      const data = (await res.json()) as { install_url: string }
      window.location.assign(data.install_url)
    } catch {
      setError("Could not prepare the GitHub connection")
    } finally {
      setConnecting(false)
    }
  }

  const installationName = useCallback(
    (repo: Repo) => {
      // full_name is "owner/name" — the owner half matches the installation's
      // account login for display purposes.
      const owner = repo.full_name.split("/", 1)[0]
      const match = installations?.find((i) => i.account_login === owner)
      return match ? `${match.account_login} (${match.account_type})` : owner
    },
    [installations]
  )

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xs font-semibold uppercase tracking-widest text-primary">
          Settings · Repositories
        </h1>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Back to dashboard
        </Button>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {repos === null || installations === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <Card>
          <CardContent className="space-y-4 p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Repositories ({repos.length})
              </h2>
              <Button
                size="sm"
                onClick={() => setAddOpen(true)}
                disabled={installations.length === 0}
              >
                Add repositories
              </Button>
            </div>
            {repos.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No repositories yet. Connect GitHub or add repositories from a connected
                installation.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {repos.map((repo) => (
                  <li key={repo.id} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{repo.full_name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        via {installationName(repo)}
                      </p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(repo)}>
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            )}

            <div className="flex items-center justify-between border-t border-border pt-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Connected GitHub accounts
              </h2>
              <Button size="sm" variant="outline" onClick={connectGitHub} disabled={connecting}>
                + Connect GitHub
              </Button>
            </div>
            {installations.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No GitHub accounts connected to this workspace yet.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {installations.map((installation) => (
                  <li
                    key={installation.installation_id}
                    className="flex items-center justify-between gap-3 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{installation.account_login}</p>
                      <p className="text-xs text-muted-foreground">
                        {installation.account_type} · {installation.repo_count} repo
                        {installation.repo_count === 1 ? "" : "s"} tracked
                        {installation.removed ? " · uninstalled on GitHub" : ""}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setConfirmUnlink(installation)}
                    >
                      Unlink
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {installations ? (
        <AddReposModal
          open={addOpen}
          onOpenChange={setAddOpen}
          installations={installations}
          onAdded={reload}
        />
      ) : null}

      <ConfirmDialog
        open={confirmRemove !== null}
        onOpenChange={(o) => {
          if (!o) setConfirmRemove(null)
        }}
        title={`Remove ${confirmRemove?.full_name ?? "repository"}?`}
        description="The repository disappears from this workspace's dashboard; historical data is retained but hidden. You can add it back later."
        confirmLabel="Remove repository"
        destructive
        onConfirm={() => confirmRemove && removeRepo(confirmRemove)}
      />

      <ConfirmDialog
        open={confirmUnlink !== null}
        onOpenChange={(o) => {
          if (!o) setConfirmUnlink(null)
        }}
        title={`Unlink ${confirmUnlink?.account_login ?? "installation"}?`}
        description="All of this installation's repositories are removed from this workspace; historical data is retained but hidden. Other workspaces using the installation are unaffected."
        confirmLabel="Unlink installation"
        destructive
        onConfirm={() => confirmUnlink && unlinkInstallation(confirmUnlink)}
      />
    </main>
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
