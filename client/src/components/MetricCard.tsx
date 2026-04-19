import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

interface Props {
  title: string
  value: string
  caption: string
  loading?: boolean
  setupRequired?: boolean
  muted?: boolean
  error?: string | null
  onRetry?: () => void
}

export function MetricCard({
  title,
  value,
  caption,
  loading,
  setupRequired,
  muted,
  error,
  onRetry,
}: Props) {
  return (
    <Card className="gap-0 py-0">
      <CardContent className="p-5">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {title}
        </p>
        {loading ? (
          <Skeleton className="h-12 w-24" />
        ) : error ? (
          <div className="space-y-2">
            <p className="text-sm text-error">Failed to load</p>
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry}>
                Retry
              </Button>
            )}
          </div>
        ) : setupRequired ? (
          <p className="text-sm text-muted-foreground">
            Requires a connected production environment
          </p>
        ) : (
          <>
            <p
              className={
                muted
                  ? "text-5xl font-extrabold leading-none tracking-tight text-muted-foreground"
                  : "text-5xl font-extrabold leading-none tracking-tight"
              }
            >
              {value}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">{caption}</p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
