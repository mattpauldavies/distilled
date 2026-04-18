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
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Your data is on its way</DialogTitle>
          <DialogDescription>
            We've detected this repository and are crunching through its history. Metrics typically
            appear within a few minutes — feel free to come back shortly.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={() => handleOpenChange(false)}>Got it</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
