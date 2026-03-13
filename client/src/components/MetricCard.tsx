import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  title: string;
  value: string;
  caption: string;
  subLabel?: string;
  loading?: boolean;
  setupRequired?: boolean;
}

export function MetricCard({
  title,
  value,
  caption,
  subLabel,
  loading,
  setupRequired,
}: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-20" />
        ) : setupRequired ? (
          <p className="text-sm text-muted-foreground">
            Configure a production environment to see this metric
          </p>
        ) : (
          <>
            <p className="text-3xl font-bold">{value}</p>
            {subLabel && (
              <p className="text-sm text-muted-foreground">{subLabel}</p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">{caption}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
