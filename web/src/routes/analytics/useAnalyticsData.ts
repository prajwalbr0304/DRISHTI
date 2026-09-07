import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { PatternType } from "@/api/types";
import { useSeatKey } from "@/hooks/useSeatKey";

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

/** Reference lookups for the scope selectors (districts / crime heads / sub-heads).
 *
 *  Confined server-side to the caller's seat, so the SEAT is part of the cache
 *  identity — two SPs share a role and are entitled to different districts, and
 *  keying by role alone served the first one's list to the second. Shares its key
 *  with `useDistricts`, so the region selector and the Analytics scope pickers are
 *  guaranteed to offer the same districts from one request. */
export function useFilterOptions() {
  const seatKey = useSeatKey();
  return useQuery({
    queryKey: ["cases", "filters", seatKey],
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

/** Rolling-origin backtest: model error vs baselines, coverage, geographic
 *  holdout. Read-only (persist=false) so the analytics screen never mutates.
 *
 *  `enabled` exists because this is the most EXPENSIVE read on the platform: it
 *  scores a rolling-origin evaluation over held-out district-months, and behind
 *  the API gateway it can exceed the upstream timeout outright. Only three cards
 *  consume it (WAPE, 80% interval coverage, abstention) and they appear on three
 *  boards, but `useKpiValues` runs on EVERY board — so left ungated it fired a
 *  model job on an SHO's and an IO's dashboard that nothing there would render.
 *  Defaults to true so the analytics Forecasts mode, which is the screen actually
 *  about model trust, needs no argument. */
export function useForecastBacktest(
  headId?: number,
  horizon = 1,
  nOrigins = 6,
  enabled = true,
) {
  return useQuery({
    queryKey: ["forecast", "backtest", headId ?? null, horizon, nOrigins],
    queryFn: ({ signal }) =>
      api.forecast.backtest(
        { head_id: headId, horizon, n_origins: nOrigins, per_head: true, persist: false },
        signal,
      ),
    enabled,
    staleTime: 10 * 60_000,
    retry: false,
  });
}

/** Data-as-of per source + approved external context + valid-geography scope. */
export function useForecastFreshness() {
  return useQuery({
    queryKey: ["forecast", "freshness"],
    queryFn: ({ signal }) => api.forecast.freshness(signal),
    staleTime: 5 * 60_000,
    retry: false,
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
