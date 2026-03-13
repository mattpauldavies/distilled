import type { DataQuality } from "@/types/dashboard";

interface Props {
  data: DataQuality;
}

function freshnessColor(status: string): string {
  if (status === 'ok') return 'text-green-600';
  if (status === 'stale') return 'text-red-600';
  return '';
}

function formatEnvList(envs: string[]): string {
  if (envs.length === 1) return envs[0];
  if (envs.length === 2) return `${envs[0]} and ${envs[1]}`;
  if (envs.length === 3) return `${envs.slice(0, 2).join(', ')} and ${envs[2]}`;
  return `${envs.slice(0, 3).join(', ')}, +${envs.length - 3} more`;
}

function timeAgo(isoString: string | null): string {
  if (!isoString) return "Never";
  const diff = Date.now() - new Date(isoString).getTime();
  if (diff < 0) return "Just now";
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function DataQualityPanel({ data }: Props) {
  const productionEnvs = data.setup.production_environments;
  const envsDisplay = formatEnvList(productionEnvs);
  
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground text-center">
      Aggregated metrics were calculated <span className="font-mono font-semibold" style={{ wordSpacing: '-3px' }}>{timeAgo(data.freshness.last_refresh_at)}</span> and are{' '}
      <span className={freshnessColor(data.freshness.status) + ' font-semibold'}>
        {data.freshness.status}
      </span>.{' '}
      {data.setup.has_production_environment ? (
        <span>Deployments to the <span className="font-mono font-semibold" style={{ wordSpacing: '-6px' }}>{envsDisplay}</span> environment{productionEnvs.length > 1 ? 's' : ''} are being tracked.</span>
      ) : (
        <span>Deployments are not being tracked.</span>
      )}
      <span className="font-mono font-semibold" style={{ wordSpacing: '-3px' }}>
      {data.attribution_coverage_percent != null
        ? ` ${data.attribution_coverage_percent.toFixed(1)}% `
          : " We're not sure what percentage "}
      </span>
      of merged pull requests are linked to a deployment.
    </div>
  );
}
