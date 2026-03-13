import { useCallback, useEffect, useState } from "react";
import type { UnifiedDashboardResponse, DaysWindow } from "@/types/dashboard";

export function useDashboard(repoId: string | null, daysWindow: DaysWindow) {
  const [data, setData] = useState<UnifiedDashboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetchKey, setFetchKey] = useState(0);

  const retry = useCallback(() => setFetchKey((k) => k + 1), []);

  useEffect(() => {
    if (!repoId) {
      setData(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    async function fetchDashboard() {
      try {
        const res = await fetch(
          `/api/metrics/unified?repo_id=${repoId}&window=${daysWindow}`
        );
        if (!res.ok) throw new Error(`Failed to load metrics: ${res.status}`);
        const json: UnifiedDashboardResponse = await res.json();
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
          setData(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchDashboard();
    return () => { cancelled = true; };
  }, [repoId, daysWindow, fetchKey]);

  return { data, loading, error, retry };
}
