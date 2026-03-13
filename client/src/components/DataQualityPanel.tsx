import { Badge } from "@/components/ui/badge";
import type { DataQuality } from "@/types/dashboard";

interface Props {
  data: DataQuality;
}

function timeAgo(isoString: string | null): string {
  if (!isoString) return "Never";
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function freshnessVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "ok") return "default";
  if (status === "stale") return "secondary";
  return "destructive";
}

export function DataQualityPanel({ data }: Props) {
  const envNames = data.setup.production_environments;
  const displayEnvs =
    envNames.length <= 3
      ? envNames.join(", ")
      : `${envNames.slice(0, 3).join(", ")} +${envNames.length - 3} more`;

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <h3 className="mb-3 text-sm font-medium text-muted-foreground">
        Data Quality
      </h3>
      <div className="flex flex-wrap gap-6 text-sm">
        <div>
          <span className="text-muted-foreground">Attribution Coverage: </span>
          <Badge variant="secondary">
            {data.attribution_coverage_percent != null
              ? `${data.attribution_coverage_percent.toFixed(1)}%`
              : "N/A"}
          </Badge>
        </div>
        <div>
          <span className="text-muted-foreground">Freshness: </span>
          <Badge variant={freshnessVariant(data.freshness.status)}>
            {data.freshness.status}
          </Badge>
          <span className="ml-1 text-muted-foreground">
            {timeAgo(data.freshness.last_refresh_at)}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">Production: </span>
          {data.setup.has_production_environment ? (
            <>
              <Badge variant="default">Configured</Badge>
              {displayEnvs && (
                <span className="ml-1 text-muted-foreground">{displayEnvs}</span>
              )}
            </>
          ) : (
            <Badge variant="destructive">Not configured</Badge>
          )}
        </div>
      </div>
    </div>
  );
}
