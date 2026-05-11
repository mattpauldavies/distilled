import "@/lib/chartSetup"
import { useEffect, useState } from "react"
import * as Sentry from "@sentry/react"
import { SignedIn, SignedOut } from "@clerk/clerk-react"
import { Dashboard } from "@/components/Dashboard"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { InitialisingScreen } from "@/components/InitialisingScreen"
import { OnboardingScreen } from "@/components/OnboardingScreen"
import { ReposErrorScreen } from "@/components/ReposErrorScreen"
import { SignInPage } from "@/components/SignInPage"
import { TeamPage } from "@/components/team/TeamPage"
import { AcceptInvitePage } from "@/pages/AcceptInvitePage"
import { useRepos } from "@/hooks/useRepos"
import { TenantProvider, useTenantContext } from "@/lib/tenantContext"

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN ?? ""

function Home() {
  const { loading: tenantLoading, error: tenantError, activeTenant } = useTenantContext()
  const { repos, loading, error, refetch } = useRepos()
  const [showTeam, setShowTeam] = useState(false)

  useEffect(() => {
    if (SENTRY_DSN) {
      Sentry.init({
        dsn: SENTRY_DSN,
      })
    }
  }, [])

  if (tenantLoading) return <InitialisingScreen />
  if (tenantError)
    return <ReposErrorScreen error={tenantError} onRetry={() => window.location.reload()} />
  if (!activeTenant) return <OnboardingScreen onReposDetected={refetch} />
  if (showTeam && activeTenant.role === "owner") {
    return <TeamPage onClose={() => setShowTeam(false)} />
  }
  if (loading) return <InitialisingScreen />
  if (error) return <ReposErrorScreen error={error} onRetry={refetch} />
  if (repos.length === 0) return <OnboardingScreen onReposDetected={refetch} />
  return <Dashboard repos={repos} onOpenTeam={() => setShowTeam(true)} />
}

function AcceptInviteRoute() {
  const params = new URLSearchParams(window.location.search)
  const token = params.get("token") ?? ""
  if (!token) {
    window.location.replace("/")
    return null
  }
  return <AcceptInvitePage token={token} />
}

export default function App() {
  // Minimal path-based routing: the only non-dashboard route is the
  // invitation accept page, which must work both signed-out and signed-in.
  const isAcceptInvite = window.location.pathname === "/invitations/accept"

  if (isAcceptInvite) {
    return (
      <ErrorBoundary>
        <AcceptInviteRoute />
      </ErrorBoundary>
    )
  }

  return (
    <ErrorBoundary>
      <SignedOut>
        <SignInPage />
      </SignedOut>
      <SignedIn>
        <TenantProvider>
          <Home />
        </TenantProvider>
      </SignedIn>
    </ErrorBoundary>
  )
}
