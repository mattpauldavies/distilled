import "@/lib/chartSetup"
import { SignedIn, SignedOut } from "@clerk/clerk-react"
import { Dashboard } from "@/components/Dashboard"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { SignInPage } from "@/components/SignInPage"

const HAS_CLERK = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

export default function App() {
  return (
    <ErrorBoundary>
      {HAS_CLERK ? (
        <>
          <SignedOut>
            <SignInPage />
          </SignedOut>
          <SignedIn>
            <Dashboard />
          </SignedIn>
        </>
      ) : (
        <Dashboard />
      )}
    </ErrorBoundary>
  )
}
