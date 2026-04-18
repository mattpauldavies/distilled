import { Button } from "@/components/ui/button"

interface ReposErrorScreenProps {
  error: string
  onRetry: () => void
}

export function ReposErrorScreen({ error, onRetry }: ReposErrorScreenProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6">
      <div
        role="alert"
        className="w-full max-w-md space-y-4 rounded-md border border-error-border bg-error-surface p-6 text-sm text-error"
      >
        <p>{error}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      </div>
    </main>
  )
}
