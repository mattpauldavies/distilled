import { useEffect, useRef, useState } from "react"
import { SignIn, useAuth } from "@clerk/clerk-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { makeApiFetch } from "@/lib/api"
import { ACTIVE_WORKSPACE_STORAGE_KEY } from "@/lib/workspaceContext"

interface Props {
  installationId: number
  state: string
  /** Delay between claim polls while GitHub confirms an org install. */
  pollIntervalMs?: number
}

type State =
  | { kind: "idle" }
  | { kind: "claiming" }
  | { kind: "waiting" }
  | { kind: "ok" }
  | { kind: "error"; message: string }

// Org installations are bound server-side by the installation webhook's
// GitHub-verified sender; the claim endpoint answers 202 until that lands.
// GitHub webhooks normally arrive within seconds, so ~40s of polling is
// generous before we hand the user guidance instead.
const MAX_POLLS = 20

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * GitHub App Setup URL callback. GitHub redirects here after an install or
 * re-configure with ?installation_id=…&state=<intent nonce>. Claiming the
 * intent binds the installation to the workspace it was minted for, then we
 * land on that workspace's dashboard.
 */
export function GitHubSetupPage({ installationId, state: nonce, pollIntervalMs = 2000 }: Props) {
  const { isSignedIn, getToken, isLoaded } = useAuth()
  const [state, setState] = useState<State>({ kind: "idle" })
  // Start-once guard as a ref, NOT state in the effect deps: setState inside
  // the effect would re-run it and the cleanup would cancel the in-flight
  // claim before its response arrived.
  const startedRef = useRef(false)

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    if (startedRef.current) return
    startedRef.current = true

    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ kind: "claiming" })

    const apiFetch = makeApiFetch(getToken)

    const claim = async () => {
      for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
        const res = await apiFetch("/installations/claim", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ installation_id: installationId, state: nonce }),
        })
        if (cancelled) return

        if (res.status === 202) {
          setState({ kind: "waiting" })
          await sleep(pollIntervalMs)
          if (cancelled) return
          continue
        }

        if (!res.ok) {
          const body = await res.text()
          let detail = body
          try {
            const json = JSON.parse(body) as { detail?: string }
            if (json.detail) detail = json.detail
          } catch {
            /* keep raw body */
          }
          setState({ kind: "error", message: detail || `Connection failed: ${res.status}` })
          return
        }

        const data = (await res.json()) as { workspace_id: string }
        // Land on the workspace the installation was bound to.
        try {
          window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, data.workspace_id)
        } catch {
          /* ignore */
        }
        window.location.replace("/")
        setState({ kind: "ok" })
        return
      }

      setState({
        kind: "error",
        message:
          "GitHub's confirmation is taking longer than expected. " +
          "If you were connecting an organisation, adjusting the repository " +
          "selection on GitHub (and saving) sends the confirmation again.",
      })
    }

    claim().catch((err: unknown) => {
      if (cancelled) return
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not connect the installation",
      })
    })
    return () => {
      cancelled = true
    }
  }, [isLoaded, isSignedIn, getToken, installationId, nonce, pollIntervalMs])

  if (!isLoaded) {
    return null
  }

  if (!isSignedIn) {
    const returnUrl = `/github/setup?installation_id=${installationId}&state=${encodeURIComponent(nonce)}`
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6">
        <SignIn redirectUrl={returnUrl} />
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardContent className="space-y-3 p-6 text-center">
          {state.kind === "claiming" || state.kind === "idle" ? (
            <>
              <h1 className="text-lg font-semibold">Connecting GitHub…</h1>
              <p className="text-sm text-muted-foreground">
                Linking the installation to your workspace and syncing repositories.
              </p>
            </>
          ) : state.kind === "waiting" ? (
            <>
              <h1 className="text-lg font-semibold">Waiting for GitHub…</h1>
              <p className="text-sm text-muted-foreground">
                Waiting for GitHub to confirm the installation. This usually takes a few seconds.
              </p>
            </>
          ) : state.kind === "error" ? (
            <>
              <h1 className="text-lg font-semibold">We couldn’t connect that installation</h1>
              <p className="text-sm text-muted-foreground">{state.message}</p>
              <p className="text-sm text-muted-foreground">
                Return to Distilled and reconnect GitHub from your workspace to get a fresh link.
              </p>
              <Button onClick={() => window.location.replace("/")}>Go to dashboard</Button>
            </>
          ) : (
            <h1 className="text-lg font-semibold">All set — redirecting…</h1>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
