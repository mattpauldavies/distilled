import "@/lib/chartSetup"
import { useState } from "react"
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
import { WorkspaceProvider, useWorkspaceContext } from "@/lib/workspaceContext"

function Home() {
  const {
    loading: workspaceLoading,
    error: workspaceError,
    activeWorkspace,
  } = useWorkspaceContext()
  const { repos, loading, error, refetch } = useRepos()
  const [showTeam, setShowTeam] = useState(false)

  if (workspaceLoading) return <InitialisingScreen />
  if (workspaceError)
    return <ReposErrorScreen error={workspaceError} onRetry={() => window.location.reload()} />
  if (!activeWorkspace) return <OnboardingScreen onReposDetected={refetch} />
  if (showTeam && activeWorkspace.role === "owner") {
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
        <WorkspaceProvider>
          <Home />
        </WorkspaceProvider>
      </SignedIn>
    </ErrorBoundary>
  )
}
