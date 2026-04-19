import { useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

const STORAGE_KEY_PREFIX = "distilled:cold-start-dismissed:"

function storageKey(repoId: string) {
  return STORAGE_KEY_PREFIX + repoId
}

function isDismissed(repoId: string): boolean {
  return localStorage.getItem(storageKey(repoId)) === "1"
}

interface NoMetricsYetDialogProps {
  repoId: string
  lastRefreshAt: string | null | undefined
}

export function NoMetricsYetDialog({ repoId, lastRefreshAt }: NoMetricsYetDialogProps) {
  const shouldShow = lastRefreshAt === null
  const [dismissed, setDismissed] = useState(() => isDismissed(repoId))

  useEffect(() => {
    setDismissed(isDismissed(repoId))
  }, [repoId])

  const open = shouldShow && !dismissed

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      localStorage.setItem(storageKey(repoId), "1")
      setDismissed(true)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Your data is on its way!</DialogTitle>
          <DialogDescription>
            We&apos;re watching this repository and waiting for data to arrive.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>
            As your team interacts with the repository we&apos;ll capture the activity here. (Note:
            We don&apos;t lookup historic data.)
          </p>
          <p>You can trigger activity manually with:</p>
          <pre className="overflow-x-auto rounded-md border border-separator bg-background p-3 text-xs leading-relaxed text-foreground">
            <code>{`git checkout -b track-with-distilled
printf '\\n> Delivery metrics for this repository are tracked with Distilled.\\n' >> README.md
git add README.md
git commit -m "docs: note metrics are tracked with Distilled"
git push -u origin track-with-distilled
gh pr create --fill`}</code>
          </pre>
        </div>
        <DialogFooter>
          <Button onClick={() => handleOpenChange(false)}>Got it</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
