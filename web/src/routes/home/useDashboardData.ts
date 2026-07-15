import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { useTimeStore } from "@/stores/useTimeStore";

/* ============================================================================
   Shared Command Center data hooks. Every home composes these; react-query
   dedupes by key so two widgets reading the same endpoint share one request.
   All data is LIVE from the Wave-B services and scoped server-side by X-Role.
   ========================================================================== */

/** Aggregate crime trend (monthly counts + rolling band + MoM/YoY) for the window. */
export function useTrends() {
  const { start, end } = useTimeStore();
  return useQuery({
    queryKey: ["geo", "trends", start, end],
    queryFn: ({ signal }) => api.geo.trends({ start, end, window: 6, decompose: false }, signal),
  });
}

/** Hotspots for the window (carry district + centroid + intensity). */
export function useHotspots() {
  const { start, end } = useTimeStore();
  return useQuery({
    queryKey: ["geo", "hotspots", start, end],
    queryFn: ({ signal }) => api.geo.hotspots({ start, end, limit: 500 }, signal),
  });
}

/** Active alerts (no time param — these are the live queue). */
export function useAlerts() {
  return useQuery({
    queryKey: ["geo", "alerts"],
    queryFn: ({ signal }) => api.geo.alerts({ limit: 200 }, signal),
    refetchInterval: 120_000,
  });
}

/** Persons of interest by graph centrality (network-of-interest shortcut). */
export function useCentrality(top = 20) {
  return useQuery({
    queryKey: ["graph", "centrality", top],
    queryFn: ({ signal }) => api.graph.centrality(top, "person", signal),
  });
}

/** Socio-economic correlations + narrative for the window (policymaker turf). */
export function useSocio() {
  const { start, end } = useTimeStore();
  return useQuery({
    queryKey: ["analytics", "socio", start, end],
    queryFn: ({ signal }) => api.analytics.socioeconomic({ start, end }, signal),
  });
}

/** Fused forecast cells (read-only) — aggregated to district level by widgets. */
export function useForecastMap() {
  return useQuery({
    queryKey: ["forecast", "map", "fused"],
    queryFn: ({ signal }) => api.forecast.map({ layer: "fused" }, signal),
  });
}
