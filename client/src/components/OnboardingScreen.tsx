import { useEffect, useRef, useState } from "react"
import { useApiFetch, useWorkspaceContext } from "@/lib/workspaceContext"
import type { Repo, PaginatedResponse } from "@/types/dashboard"

const DEFAULT_POLL_INTERVAL_MS = 5000

interface OnboardingScreenProps {
  onReposDetected: () => void
  pollIntervalMs?: number
}

export function OnboardingScreen({
  onReposDetected,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}: OnboardingScreenProps) {
  const apiFetch = useApiFetch()
  const { activeWorkspace } = useWorkspaceContext()
  const isOwner = activeWorkspace?.role === "owner"

  const [installUrl, setInstallUrl] = useState<string | null>(null)
  const [intentError, setIntentError] = useState(false)
  // Mint exactly one intent per mount cycle: StrictMode double-fires the
  // effect, and a second concurrent mint supersedes the first — leaving the
  // rendered install link carrying a dead nonce.
  const mintedRef = useRef(false)

  // The install link carries a workspace-bound state nonce, so GitHub's
  // redirect (and the webhook sender) can bind the installation to THIS
  // workspace rather than inferring one.
  useEffect(() => {
    if (!isOwner || mintedRef.current) return
    mintedRef.current = true
    let cancelled = false
    apiFetch("/installations/intents", { method: "POST" })
      .then(async (res) => {
        if (cancelled) return
        if (!res.ok) {
          setIntentError(true)
          return
        }
        const data = (await res.json()) as { install_url: string }
        setInstallUrl(data.install_url)
        setIntentError(false)
      })
      .catch(() => {
        if (!cancelled) setIntentError(true)
      })
    return () => {
      cancelled = true
    }
  }, [apiFetch, isOwner])

  useEffect(() => {
    const intervalId = setInterval(async () => {
      try {
        const res = await apiFetch("/repos?limit=1")
        if (!res.ok) return
        const data: PaginatedResponse<Repo> = await res.json()
        if (data.items.length > 0) {
          clearInterval(intervalId)
          onReposDetected()
        }
      } catch {
        // silently ignore poll errors
      }
    }, pollIntervalMs)

    return () => clearInterval(intervalId)
  }, [apiFetch, onReposDetected, pollIntervalMs])

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="w-full max-w-lg space-y-8">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">Welcome to Distilled</h1>
          <p className="text-muted-foreground">
            Connect your GitHub repositories to start tracking your engineering delivery metrics.
          </p>
        </div>

        <div className="rounded-lg border border-separator bg-surface p-6 space-y-4">
          <div className="space-y-1">
            <h2 className="font-semibold">Step 1: Install the Distilled GitHub App</h2>
            <p className="text-sm text-muted-foreground">
              Grant access to the repositories you want to track. You can add more repos later.
            </p>
          </div>
          {isOwner ? (
            installUrl ? (
              <a
                href={installUrl}
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                Install GitHub App →
              </a>
            ) : intentError ? (
              <p className="text-sm text-destructive">
                Could not prepare the GitHub connection. Refresh the page to try again.
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">Preparing GitHub connection…</p>
            )
          ) : (
            <p className="text-sm text-muted-foreground">
              Ask the workspace owner to connect GitHub — only owners can install repositories.
            </p>
          )}
        </div>

        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Already installed?</span> Then we're just
            waiting for data…
            <br />
            Repos appear here within a few seconds of completing the GitHub App installation.
          </p>
        </div>

        <p className="text-sm text-muted-foreground">
          Read the{" "}
          <a
            href="https://distilledmetrics.com/getting-started"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-foreground underline underline-offset-4 hover:opacity-80"
          >
            Getting Started Guide
          </a>{" "}
          to learn how Distilled tracks your delivery metrics.
        </p>
      </div>
    </main>
  )
}
