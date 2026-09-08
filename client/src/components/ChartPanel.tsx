import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { InfoButton } from "@/components/InfoButton"
import type { ReactNode } from "react"

interface Props {
  title: string
  caption: string
  loading?: boolean
  empty?: boolean
  emptyMessage?: string
  info?: string
  error?: string | null
  onRetry?: () => void
  children: ReactNode
}

export function ChartPanel({
  title,
  caption,
  loading,
  empty,
  emptyMessage = "No data available",
  info,
  error,
  onRetry,
  children,
}: Props) {
  return (
    <Card className="gap-2 py-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        <p className="text-xs text-muted-foreground">{caption}</p>
        {info && (
          <CardAction>
            <InfoButton content={info} />
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-[220px] w-full" />
        ) : error ? (
          <div className="flex h-[220px] flex-col items-center justify-center gap-2">
            <p className="text-sm text-error">Failed to load</p>
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry}>
                Retry
              </Button>
            )}
          </div>
        ) : empty ? (
          <div className="flex h-[220px] items-center justify-center">
            <p className="text-sm text-muted-foreground">{emptyMessage}</p>
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  )
}
