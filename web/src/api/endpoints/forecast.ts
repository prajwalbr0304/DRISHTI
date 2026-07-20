import { apiClient } from "@/api/client";
import type {
  BacktestResponse,
  DistrictForecastResponse,
  ForecastMapResponse,
  ForecastRunResponse,
  FreshnessResponse,
  LayersResponse,
  NearRepeatTriggerResponse,
  ValidationResponse,
} from "@/api/types";

export type ForecastLayerId = "tabfm" | "timesfm" | "near_repeat" | "st_gnn" | "fused";

export interface ForecastMapParams {
  layer?: ForecastLayerId;
  head_id?: number;
  min_lon?: number;
  min_lat?: number;
  max_lon?: number;
  max_lat?: number;
}

/** Phase-12 forecasting + early warning (services/ml/app/forecast). */
export const forecastApi = {
  run: (head_id?: number, horizon_days = 30, signal?: AbortSignal) =>
    apiClient.post<ForecastRunResponse>("/forecast/run", undefined, { head_id, horizon_days }, signal),

  layers: (signal?: AbortSignal) =>
    apiClient.get<LayersResponse>("/forecast/layers", undefined, signal),

  district: (district_id: number, head_id?: number, layer?: ForecastLayerId, signal?: AbortSignal) =>
    apiClient.get<DistrictForecastResponse>(
      `/forecast/district/${district_id}`,
      { head_id, layer },
      signal,
    ),

  map: (params: ForecastMapParams = {}, signal?: AbortSignal) =>
    apiClient.get<ForecastMapResponse>("/forecast/map", { layer: "fused", ...params }, signal),

  nearRepeat: (
    lat: number,
    lon: number,
    opts: { district_id?: number; head_id?: number } = {},
    signal?: AbortSignal,
  ) =>
    apiClient.post<NearRepeatTriggerResponse>(
      "/forecast/near-repeat",
      undefined,
      { lat, lon, ...opts },
      signal,
    ),

  validation: (
    opts: { cutoff?: string; horizon_months?: number; area_fraction?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<ValidationResponse>("/forecast/validation", opts, signal),

  /** Rolling-origin backtest: MAE/RMSE/WAPE/sMAPE + interval coverage + baseline
   *  comparison + geographic holdout. Read-only unless persist=true. */
  backtest: (
    opts: { head_id?: number; horizon?: number; n_origins?: number; per_head?: boolean; persist?: boolean } = {},
    signal?: AbortSignal,
  ) => apiClient.get<BacktestResponse>("/forecast/backtest", opts, signal),

  /** Data-as-of per source + approved external context + valid-geography scope. */
  freshness: (signal?: AbortSignal) =>
    apiClient.get<FreshnessResponse>("/forecast/freshness", undefined, signal),

  /** Prompt 20 §F — advertised forecast horizons + how each is validated.
   *  Day-ahead crime forecasting is declared future work (no held-out eval);
   *  7/14-day views are a transparent linear scaling of the validated 30-day base. */
  horizons: (signal?: AbortSignal) =>
    apiClient.get<Record<string, unknown>>("/forecast/horizons", undefined, signal),
};
