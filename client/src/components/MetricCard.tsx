import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

interface Props {
  title: string
  value: string
  caption: string
  loading?: boolean
  setupRequired?: boolean
  muted?: boolean
}

export function MetricCard({ title, value, caption, loading, setupRequired, muted }: Props) {
  return (
    <Card className="gap-0 py-0">
      <CardContent className="p-5">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {title}
        </p>
        {loading ? (
          <Skeleton className="h-12 w-24" />
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
