import { apiClient } from "@/api/client";
import type { CalibrationResponse, RiskResponse } from "@/api/types";

/** Phase-9 offender risk scoring (services/ml/app/risk). */
export const riskApi = {
  calibration: (signal?: AbortSignal) =>
    apiClient.get<CalibrationResponse>("/risk/calibration", undefined, signal),

  byEntity: (entity_id: number, rescore = false, signal?: AbortSignal) =>
    apiClient.get<RiskResponse>(`/risk/entity/${entity_id}`, { rescore }, signal),

  byAccused: (accused_id: number, signal?: AbortSignal) =>
    apiClient.get<RiskResponse>(`/risk/${accused_id}`, undefined, signal),
};
