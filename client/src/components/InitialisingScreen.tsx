export function InitialisingScreen() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <div role="status" aria-live="polite" className="text-sm text-muted-foreground">
        Initialising…
      </div>
    </main>
  )
}
