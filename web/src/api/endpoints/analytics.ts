import { apiClient } from "@/api/client";
import type { CrimePatternsResponse, PatternType, SocioEconomicResponse } from "@/api/types";

export type SocioParams = {
  start?: string;
  end?: string;
  k_threshold?: number;
  focus_indicator?: string;
};

export type PatternParams = {
  pattern_type?: PatternType;
  crime_head_id?: number;
  limit?: number;
};

/** Phase-8 socio-economic + Phase-7 crime-pattern analytics (services/ml/app/analytics). */
export const analyticsApi = {
  socioeconomic: (params: SocioParams = {}, signal?: AbortSignal) =>
    apiClient.get<SocioEconomicResponse>("/analytics/socioeconomic", params, signal),

  /** GET /analytics/patterns — detected crime patterns + their evidencing FIRs. */
  patterns: (params: PatternParams = {}, signal?: AbortSignal) =>
    apiClient.get<CrimePatternsResponse>("/analytics/patterns", params, signal),
};
