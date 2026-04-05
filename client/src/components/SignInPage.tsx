import { SignIn } from "@clerk/clerk-react"

export function SignInPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <SignIn
        appearance={{
          elements: {
            footer: {
              display: 'none',
            },
          },
        }}
      />
    </main>
  )
}
