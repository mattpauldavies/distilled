import "@/lib/chartSetup"
import { SignedIn, SignedOut } from "@clerk/clerk-react"
import { Dashboard } from "@/components/Dashboard"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { SignInPage } from "@/components/SignInPage"

export default function App() {
  return (
    <ErrorBoundary>
      <SignedOut>
        <SignInPage />
      </SignedOut>
      <SignedIn>
        <Dashboard />
      </SignedIn>
    </ErrorBoundary>
  )
}
