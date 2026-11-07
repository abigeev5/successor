import { useQuery } from "@tanstack/react-query";

import {
  api,
  unwrap,
  type AuditEntry,
  type HandoverProgress,
  type Metrics,
  type RiskMap,
} from "./client";

export function useRiskMap() {
  return useQuery<RiskMap>({
    queryKey: ["dashboard", "risk"],
    queryFn: async () => unwrap(await api.GET("/api/dashboard/risk")),
  });
}

export function useProgress(handoverId: string | undefined, enabled = true) {
  return useQuery<HandoverProgress>({
    queryKey: ["progress", handoverId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/handovers/{handover_id}/progress", {
          params: { path: { handover_id: handoverId! } },
        }),
      ),
    enabled: !!handoverId && enabled,
  });
}

/** Scope and period of the metrics block; empty strings mean «all». */
export type MetricsFilter = { handoverId: string; from: string; to: string };

function metricsQuery(filter: MetricsFilter) {
  return {
    ...(filter.handoverId && { handover_id: filter.handoverId }),
    ...(filter.from && { from: filter.from }),
    ...(filter.to && { to: filter.to }),
  };
}

export function useMetrics(filter: MetricsFilter) {
  return useQuery<Metrics>({
    queryKey: ["dashboard", "metrics", filter],
    queryFn: async () =>
      unwrap(await api.GET("/api/dashboard/metrics", { params: { query: metricsQuery(filter) } })),
  });
}

/** A plain link: the browser downloads the file with the session cookie. */
export function metricsCsvUrl(filter: MetricsFilter): string {
  const query = new URLSearchParams(metricsQuery(filter)).toString();
  return `/api/dashboard/metrics.csv${query ? `?${query}` : ""}`;
}

export function useAuditLog(entity: string) {
  return useQuery<AuditEntry[]>({
    queryKey: ["audit", entity],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/audit", {
          params: { query: { ...(entity && { entity }), limit: 200 } },
        }),
      ),
  });
}
