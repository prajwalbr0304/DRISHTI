import { apiClient } from "@/api/client";
import type {
  DistrictForecastResponse,
  ForecastMapResponse,
  ForecastRunResponse,
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
};
