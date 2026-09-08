import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import * as Sentry from "@sentry/react"
import { ClerkProvider } from "@clerk/clerk-react"
import { shadcn } from "./lib/clerkTheme"
import "./index.css"
import App from "./App"

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN ?? ""
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
  })
}

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClerkProvider
      publishableKey={publishableKey}
      appearance={{
        theme: shadcn,
      }}
    >
      <App />
    </ClerkProvider>
  </StrictMode>
)
