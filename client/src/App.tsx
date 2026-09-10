import "@/lib/chartSetup"
import { useState } from "react"
import { SignedIn, SignedOut } from "@clerk/clerk-react"
import { Dashboard } from "@/components/Dashboard"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { InitialisingScreen } from "@/components/InitialisingScreen"
import { NoWorkspaceScreen } from "@/components/NoWorkspaceScreen"
import { OnboardingScreen } from "@/components/OnboardingScreen"
import { ReposErrorScreen } from "@/components/ReposErrorScreen"
import { SignInPage } from "@/components/SignInPage"
import { RepositoriesPage } from "@/components/repos/RepositoriesPage"
import { TeamPage } from "@/components/team/TeamPage"
import { AcceptInvitePage } from "@/pages/AcceptInvitePage"
import { GitHubSetupPage } from "@/pages/GitHubSetupPage"
import { useRepos } from "@/hooks/useRepos"
import { WorkspaceProvider, useWorkspaceContext } from "@/lib/workspaceContext"

function Home() {
  const {
    loading: workspaceLoading,
    error: workspaceError,
    activeWorkspace,
  } = useWorkspaceContext()
  const { repos, loading, error, refetch } = useRepos()
  const [settingsPage, setSettingsPage] = useState<"none" | "team" | "repos">("none")

  if (workspaceLoading) return <InitialisingScreen />
  if (workspaceError)
    return <ReposErrorScreen error={workspaceError} onRetry={() => window.location.reload()} />
  if (!activeWorkspace) return <NoWorkspaceScreen />
  if (settingsPage === "team" && activeWorkspace.role === "owner") {
    return <TeamPage onClose={() => setSettingsPage("none")} />
  }
  if (settingsPage === "repos" && activeWorkspace.role === "owner") {
    return <RepositoriesPage onClose={() => setSettingsPage("none")} />
  }
  if (loading) return <InitialisingScreen />
  if (error) return <ReposErrorScreen error={error} onRetry={refetch} />
  if (repos.length === 0) return <OnboardingScreen onReposDetected={refetch} />
  return (
    <Dashboard
      repos={repos}
      onOpenTeam={() => setSettingsPage("team")}
      onOpenRepos={() => setSettingsPage("repos")}
    />
  )
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

function GitHubSetupRoute() {
  const params = new URLSearchParams(window.location.search)
  const installationId = Number(params.get("installation_id"))
  const state = params.get("state") ?? ""
  if (!installationId || !state) {
    window.location.replace("/")
    return null
  }
  return <GitHubSetupPage installationId={installationId} state={state} />
}

export default function App() {
  // Minimal path-based routing: the non-dashboard routes are the invitation
  // accept page and the GitHub App setup callback, both of which must work
  // signed-out and signed-in.
  const isAcceptInvite = window.location.pathname === "/invitations/accept"
  const isGitHubSetup = window.location.pathname === "/github/setup"

  if (isAcceptInvite) {
    return (
      <ErrorBoundary>
        <AcceptInviteRoute />
      </ErrorBoundary>
    )
  }

  if (isGitHubSetup) {
    return (
      <ErrorBoundary>
        <GitHubSetupRoute />
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
