import "@/lib/chartSetup"
import { useEffect } from "react"
import * as Sentry from "@sentry/react"
import { SignedIn, SignedOut } from "@clerk/clerk-react"
import { Dashboard } from "@/components/Dashboard"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { InitialisingScreen } from "@/components/InitialisingScreen"
import { OnboardingScreen } from "@/components/OnboardingScreen"
import { ReposErrorScreen } from "@/components/ReposErrorScreen"
import { SignInPage } from "@/components/SignInPage"
import { useRepos } from "@/hooks/useRepos"
import { TenantProvider, useTenantContext } from "@/lib/tenantContext"

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN ?? ""

function Home() {
  const { loading: tenantLoading, error: tenantError, activeTenant } = useTenantContext()
  const { repos, loading, error, refetch } = useRepos()

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
        <TenantProvider>
          <Home />
        </TenantProvider>
      </SignedIn>
    </ErrorBoundary>
  )
}
