import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { PatternType } from "@/api/types";

/* ============================================================================
   Shared data hooks for the Analytics & Forecasting destination (doc 01 §4.6).
   All live from the Wave-B services, scoped server-side by X-Role.

   NB on time: the operational data spans several years, so the Analytics panels
   read their OWN full range (they omit the 30-day global scrubber window, which
   would come back empty) — the same call the Map destination already makes.
   Scope here is by district / crime head, not by a trailing window.
   ========================================================================== */

export interface TrendScope {
  district_id?: number;
  crime_head_id?: number;
  sub_head_id?: number;
  window?: number;
  k?: number;
  decompose?: boolean;
}

/** Reference lookups for the scope selectors (districts / crime heads / sub-heads). */
export function useFilterOptions() {
  return useQuery({
    queryKey: ["cases", "filters"],
    queryFn: ({ signal }) => api.cases.filters(signal),
    staleTime: 30 * 60_000,
  });
}

/** Monthly crime-volume trend for a scope: rolling anomaly band + STL decomposition. */
export function useTrends(scope: TrendScope) {
  return useQuery({
    queryKey: ["geo", "trends", "analytics", scope],
    queryFn: ({ signal }) =>
      api.geo.trends(
        {
          district_id: scope.district_id,
          crime_head_id: scope.crime_head_id,
          sub_head_id: scope.sub_head_id,
          window: scope.window ?? 6,
          k: scope.k ?? 2,
          decompose: scope.decompose ?? true,
        },
        signal,
      ),
  });
}

/** Detected crime patterns (+ evidencing cases) for the pattern-type / head filters. */
export function usePatterns(params: { pattern_type?: PatternType; crime_head_id?: number }) {
  return useQuery({
    queryKey: ["analytics", "patterns", params],
    queryFn: ({ signal }) => api.analytics.patterns({ ...params, limit: 80 }, signal),
  });
}

/** Socio-economic correlations over the full period (correlational, not causal). */
export function useSocio(focusIndicator?: string) {
  return useQuery({
    queryKey: ["analytics", "socio", "analytics", focusIndicator ?? "auto"],
    queryFn: ({ signal }) =>
      api.analytics.socioeconomic(focusIndicator ? { focus_indicator: focusIndicator } : {}, signal),
  });
}

/** Fused forecast cells — used to discover which districts carry a forecast. */
export function useForecastFused() {
  return useQuery({
    queryKey: ["forecast", "map", "fused", "analytics"],
    queryFn: ({ signal }) => api.forecast.map({ layer: "fused" }, signal),
  });
}

/** All available forecast layers (the layer switcher + "has a forecast run" probe). */
export function useForecastLayers() {
  return useQuery({
    queryKey: ["forecast", "layers"],
    queryFn: ({ signal }) => api.forecast.layers(signal),
  });
}

/** Per-district, per-layer forecast (the timesfm layer carries the fan trajectory). */
export function useDistrictForecast(districtId: number | null, headId?: number) {
  return useQuery({
    queryKey: ["forecast", "district", districtId, headId ?? null],
    queryFn: ({ signal }) => api.forecast.district(districtId as number, headId, undefined, signal),
    enabled: districtId != null,
  });
}

/** Model registry: calibration + inference stats per ModelVersion. */
export function useModels() {
  return useQuery({
    queryKey: ["explain", "models"],
    queryFn: ({ signal }) => api.explain.models(signal),
  });
}

/** One model version's calibration + monthly drift. */
export function useModelDetail(modelVersionId: number | null) {
  return useQuery({
    queryKey: ["explain", "model", modelVersionId],
    queryFn: ({ signal }) => api.explain.modelDetail(modelVersionId as number, signal),
    enabled: modelVersionId != null,
  });
}

/** Held-out calibration of the flagship risk model vs its baseline. */
export function useRiskCalibration() {
  return useQuery({
    queryKey: ["risk", "calibration"],
    queryFn: ({ signal }) => api.risk.calibration(signal),
    retry: false,
  });
}
