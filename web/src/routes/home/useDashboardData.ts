import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { AlertResponse, ForecastMapResponse, HotspotResponse } from "@/api/types";
import { useTimeStore } from "@/stores/useTimeStore";
import { useScopeStore } from "@/stores/useScopeStore";

/* ============================================================================
   Shared Command Center data hooks. Every home composes these; react-query
   dedupes by key so two widgets reading the same endpoint share one request.
   All data is LIVE from the Wave-B services and scoped server-side by X-Role.

   DISTRICT SCOPE (the top-bar region selector) reaches these endpoints
   unevenly, and the difference is deliberate rather than hidden:

     server-side  /geo/trends, /cases/caseload take district_id, so the district
                  joins the query key and the API does the filtering.
     client-side  /geo/hotspots, /geo/alerts and /forecast/map have no district
                  param, but every row carries district_id — so the request stays
                  unscoped (one fetch, shared cache) and `select` narrows the rows.
                  Counts are recomputed so KPI cards show the scoped number.
     not at all   /analytics/socioeconomic is a correlation ACROSS districts and
                  /graph/centrality has no district in its params or response.
                  These stay state-wide; the widgets say so via STATE_WIDE_NOTE
                  rather than letting the selector imply a filter.
   ========================================================================== */

/** Aggregate crime trend (monthly counts + rolling band + MoM/YoY) for the window. */
export function useTrends() {
  const { start, end } = useTimeStore();
  const districtId = useScopeStore((s) => s.districtId);
  return useQuery({
    // district is a server-side param, so it must key the cache
    queryKey: ["geo", "trends", start, end, districtId],
    queryFn: ({ signal }) =>
      api.geo.trends(
        { start, end, window: 6, decompose: false, district_id: districtId ?? undefined },
        signal,
      ),
  });
}

/** Hotspots for the window (carry district + centroid + intensity). */
export function useHotspots() {
  const { start, end } = useTimeStore();
  const districtId = useScopeStore((s) => s.districtId);
  return useQuery({
    // NB: district deliberately absent from the key — /geo/hotspots cannot filter
    // server-side, so one unscoped fetch is shared and narrowed below.
    queryKey: ["geo", "hotspots", start, end],
    queryFn: ({ signal }) => api.geo.hotspots({ start, end, limit: 500 }, signal),
    select: (data: HotspotResponse) => {
      if (districtId == null) return data;
      const hotspots = data.hotspots.filter((h) => h.district_id === districtId);
      return { ...data, hotspots, count: hotspots.length };
    },
  });
}

/** Active alerts (no time param — these are the live queue). */
export function useAlerts() {
  const districtId = useScopeStore((s) => s.districtId);
  return useQuery({
    queryKey: ["geo", "alerts"],
    queryFn: ({ signal }) => api.geo.alerts({ limit: 200 }, signal),
    refetchInterval: 120_000,
    select: (data: AlertResponse) => {
      if (districtId == null) return data;
      const alerts = data.alerts.filter((a) => a.district_id === districtId);
      return { ...data, alerts, count: alerts.length };
    },
  });
}

/** My caseload — per-stage FIR-lifecycle counts. A present-state snapshot (no
    time window, like the alert queue); each case sits at exactly one stage. */
export function useCaseload() {
  const districtId = useScopeStore((s) => s.districtId);
  return useQuery({
    queryKey: ["cases", "caseload", districtId],
    queryFn: ({ signal }) => api.cases.caseload({ district_id: districtId ?? undefined }, signal),
  });
}

/** Persons of interest by graph centrality (network-of-interest shortcut).
    STATE-WIDE: /graph/centrality has no district in its params or its response. */
export function useCentrality(top = 20) {
  return useQuery({
    queryKey: ["graph", "centrality", top],
    queryFn: ({ signal }) => api.graph.centrality(top, "person", signal),
  });
}

/** Socio-economic correlations + narrative (policymaker turf). District-level
    correlation needs volume, so it reads the FULL operational period rather than
    the trailing scrubber window (which would be too sparse / k-anon suppressed).
    STATE-WIDE: a correlation across districts cannot be narrowed to one.

    `focusIndicator` only changes which indicator the SCATTER series are built
    for — the matrix, district count and suppression count are identical. So the
    KPI cards call this with no argument and keep the shared "auto" cache entry,
    while the chart panel re-queries when the user picks another indicator; with
    no override both land on the same key and one request serves both. */
export function useSocio(focusIndicator?: string) {
  return useQuery({
    queryKey: ["analytics", "socio", "full", focusIndicator ?? "auto"],
    queryFn: ({ signal }) =>
      api.analytics.socioeconomic(focusIndicator ? { focus_indicator: focusIndicator } : {}, signal),
  });
}

/** Fused forecast cells (read-only) — aggregated to district level by widgets. */
export function useForecastMap() {
  const districtId = useScopeStore((s) => s.districtId);
  return useQuery({
    queryKey: ["forecast", "map", "fused"],
    queryFn: ({ signal }) => api.forecast.map({ layer: "fused" }, signal),
    select: (data: ForecastMapResponse) => {
      if (districtId == null) return data;
      const cells = data.cells.filter((c) => c.district_id === districtId);
      return { ...data, cells, count: cells.length };
    },
  });
}
