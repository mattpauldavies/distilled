import { useEffect } from "react"
import { makeApiFetch } from "@/lib/api"
import { useGetToken } from "@/lib/auth"
import type { Repo, PaginatedResponse } from "@/types/dashboard"

const GITHUB_APP_SLUG = import.meta.env.VITE_GITHUB_APP_SLUG ?? ""
const INSTALL_URL = `https://github.com/apps/${GITHUB_APP_SLUG}/installations/new`
const DEFAULT_POLL_INTERVAL_MS = 5000

interface OnboardingScreenProps {
  onReposDetected: () => void
  pollIntervalMs?: number
}

export function OnboardingScreen({
  onReposDetected,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}: OnboardingScreenProps) {
  const getToken = useGetToken()

  useEffect(() => {
    const apiFetch = makeApiFetch(getToken)

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onReposDetected, pollIntervalMs])

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
          <a
            href={INSTALL_URL}
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Install GitHub App →
          </a>
        </div>

        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Already installed?</span> Then we're just waiting for
            data…
          </p>
          <p className="text-sm text-muted-foreground">
            Repos appear here within a few seconds of completing the GitHub App installation.
          </p>
        </div>

        <p className="text-sm text-muted-foreground">
          Need help? Read the{" "}
          <a
            href="https://distilledmetrics.com/getting-started.html"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-foreground underline underline-offset-4 hover:opacity-80"
          >
            Getting Started Guide
          </a>{" "}
          to learn how Distilled tracks deployments, pull requests, and your delivery metrics.
        </p>
      </div>
    </main>
  )
}
