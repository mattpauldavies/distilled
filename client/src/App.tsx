import "@/lib/chartSetup"
import { SignedIn, SignedOut } from "@clerk/clerk-react"
import { Dashboard } from "@/components/Dashboard"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { InitialisingScreen } from "@/components/InitialisingScreen"
import { OnboardingScreen } from "@/components/OnboardingScreen"
import { ReposErrorScreen } from "@/components/ReposErrorScreen"
import { SignInPage } from "@/components/SignInPage"
import { useRepos } from "@/hooks/useRepos"

function AuthedRoot() {
  const { repos, loading, error, refetch } = useRepos()

  if (loading) return <InitialisingScreen />
  if (error) return <ReposErrorScreen error={error} onRetry={refetch} />
  if (repos.length === 0) return <OnboardingScreen onReposDetected={refetch} />
  return <Dashboard repos={repos} />
}

export default function App() {
  return (
    <ErrorBoundary>
      <SignedOut>
        <SignInPage />
      </SignedOut>
      <SignedIn>
        <AuthedRoot />
      </SignedIn>
    </ErrorBoundary>
  )
}
