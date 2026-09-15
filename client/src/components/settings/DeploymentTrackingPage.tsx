import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useApiFetch } from "@/lib/workspaceContext"
import type { DeploymentSource, PaginatedResponse, Repo } from "@/types/dashboard"

interface Props {
  onClose: () => void
}

const SOURCES: { value: DeploymentSource; label: string }[] = [
  { value: "deployment", label: "Deployments" },
  { value: "release", label: "Releases" },
]

export function DeploymentTrackingPage({ onClose }: Props) {
  const apiFetch = useApiFetch()

  const [repos, setRepos] = useState<Repo[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const res = await apiFetch("/repos?limit=100")
      if (!res.ok) {
        setError("Failed to load repositories")
        return
      }
      const data = (await res.json()) as PaginatedResponse<Repo>
      setRepos(data.items)
      setError(null)
    } catch {
      setError("Failed to load repositories")
    }
  }, [apiFetch])

  useEffect(() => {
    reload()
  }, [reload])

  function applySource(repoId: string, source: DeploymentSource) {
    setRepos(
      (current) =>
        current?.map((r) => (r.id === repoId ? { ...r, deployment_source: source } : r)) ?? null
    )
  }

  async function setSource(repo: Repo, source: DeploymentSource) {
    if (repo.deployment_source === source || saving) return

    applySource(repo.id, source)
    setSaving(repo.id)
    try {
      const res = await apiFetch(`/repos/${repo.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deployment_source: source }),
      })
      if (!res.ok) throw new Error(String(res.status))
      setError(null)
    } catch {
      applySource(repo.id, repo.deployment_source)
      setError(`Could not change deployment tracking for ${repo.full_name}`)
    } finally {
      setSaving(null)
    }
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xs font-semibold uppercase tracking-widest text-primary">
          Settings · Deployment Tracking
        </h1>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Back to dashboard
        </Button>
      </div>

      <p className="text-sm text-muted-foreground">
        Choose what counts as a deployment for each repository. Deployments come from successful
        GitHub deployments to a production environment; releases come from publishing a GitHub
        release, excluding drafts and pre-releases. A change applies from the next event — nothing
        already recorded is removed.
      </p>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {repos === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <Card>
          <CardContent className="space-y-4 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Repositories ({repos.length})
            </h2>
            {repos.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No repositories yet. Add one from Settings · Repositories first.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {repos.map((repo) => (
                  <li key={repo.id} className="flex items-center justify-between gap-3 py-3">
                    <p className="min-w-0 truncate text-sm font-medium">{repo.full_name}</p>
                    <div
                      role="radiogroup"
                      aria-label={`Deployment source for ${repo.full_name}`}
                      className="flex shrink-0 rounded-md border border-border p-0.5"
                    >
                      {SOURCES.map((source) => {
                        const selected = repo.deployment_source === source.value
                        return (
                          <button
                            key={source.value}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            disabled={saving === repo.id}
                            onClick={() => setSource(repo, source.value)}
                            className={`rounded px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                              selected
                                ? "bg-muted text-foreground"
                                : "text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            {source.label}
                          </button>
                        )
                      })}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-muted-foreground">
        Release tracking needs the Distilled GitHub App&apos;s updated permissions to have been
        accepted on GitHub. Until they are, no releases reach Distilled.
      </p>
    </main>
  )
}
