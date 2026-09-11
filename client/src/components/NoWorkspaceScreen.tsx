import { useState } from "react"
import { Button } from "@/components/ui/button"
import { CreateWorkspaceModal } from "@/components/CreateWorkspaceModal"

/**
 * Shown when the signed-in user has no workspace memberships at all —
 * e.g. after deleting their last workspace or leaving every team.
 */
export function NoWorkspaceScreen() {
  const [open, setOpen] = useState(false)
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No workspace yet</h1>
          <p className="text-muted-foreground">
            Create a workspace to connect repositories and start tracking delivery metrics, or ask a
            teammate to invite you to theirs.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>Create workspace</Button>
      </div>
      <CreateWorkspaceModal open={open} onOpenChange={setOpen} />
    </main>
  )
}
