import { useEffect, useRef, useState } from "react"
import { SignIn, useAuth } from "@clerk/clerk-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { makeApiFetch } from "@/lib/api"
import { ACTIVE_WORKSPACE_STORAGE_KEY } from "@/lib/workspaceContext"

interface Props {
  token: string
}

type State =
  | { kind: "idle" }
  | { kind: "redeeming" }
  | { kind: "ok"; workspaceId: string }
  | { kind: "error"; message: string }

/**
 * Public entry for invitation links. Redemption is bundled into the first
 * sign-in: we land here, sign the user in if needed, then auto-fire
 * /invitations/redeem and route them home with the joined workspace active.
 *
 * Per the RFC: no preview, no extra confirm step. The user has already read
 * the inviter's name and workspace in the email; we don't repeat that here.
 */
export function AcceptInvitePage({ token }: Props) {
  const { isSignedIn, getToken, isLoaded } = useAuth()
  const [state, setState] = useState<State>({ kind: "idle" })
  // Start-once guard as a ref, NOT state in the effect deps: setState inside
  // the effect would re-run it and the cleanup would cancel the in-flight
  // redemption before its response arrived (dropping the redirect).
  const startedRef = useRef(false)

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    if (startedRef.current) return
    startedRef.current = true

    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ kind: "redeeming" })

    const apiFetch = makeApiFetch(getToken)
    apiFetch("/invitations/redeem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        if (cancelled) return
        if (!res.ok) {
          const body = await res.text()
          let detail = body
          try {
            const json = JSON.parse(body) as { detail?: string }
            if (json.detail) detail = json.detail
          } catch {
            /* keep raw body */
          }
          setState({ kind: "error", message: detail || `Redeem failed: ${res.status}` })
          return
        }
        const data = (await res.json()) as { workspace_id: string }
        // Store the new workspace as the active choice so the dashboard switches
        // to it on the next reload.
        try {
          window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, data.workspace_id)
        } catch {
          /* ignore */
        }
        // Hard redirect: the simplest way to drop the ?token query string and
        // re-mount the app under the new workspace context.
        window.location.replace("/")
        setState({ kind: "ok", workspaceId: data.workspace_id })
      })
      .catch((err) => {
        if (cancelled) return
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Could not redeem invitation",
        })
      })
    return () => {
      cancelled = true
    }
  }, [isLoaded, isSignedIn, getToken, token])

  if (!isLoaded) {
    return null
  }

  if (!isSignedIn) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6">
        <SignIn redirectUrl={`/invitations/accept?token=${encodeURIComponent(token)}`} />
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardContent className="space-y-3 p-6 text-center">
          {state.kind === "redeeming" || state.kind === "idle" ? (
            <>
              <h1 className="text-lg font-semibold">Joining your team…</h1>
              <p className="text-sm text-muted-foreground">Hold on while we set things up.</p>
            </>
          ) : state.kind === "error" ? (
            <>
              <h1 className="text-lg font-semibold">We couldn’t accept that invitation</h1>
              <p className="text-sm text-muted-foreground">{state.message}</p>
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
