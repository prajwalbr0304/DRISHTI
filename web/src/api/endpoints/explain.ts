import { apiClient } from "@/api/client";
import type {
  ContractAuditResponse,
  ExplainResponse,
  ModelDetailResponse,
  ModelsResponse,
} from "@/api/types";

export type ExplainableTable =
  | "CrimeRiskScore"
  | "CrimePrediction"
  | "AISummary"
  | "AlertHistory";

/** Phase-13 explainability & evidence trails (services/ml/app/explain). */
export const explainApi = {
  contract: (signal?: AbortSignal) =>
    apiClient.get<ContractAuditResponse>("/explain/contract", undefined, signal),

  models: (signal?: AbortSignal) =>
    apiClient.get<ModelsResponse>("/explain/models", undefined, signal),

  modelDetail: (model_version_id: number, signal?: AbortSignal) =>
    apiClient.get<ModelDetailResponse>(`/explain/models/${model_version_id}`, undefined, signal),

  /** GET /explain/{table}/{id} — evidence chain for an explainable row. */
  explainRow: (table: ExplainableTable, record_id: number, signal?: AbortSignal) =>
    apiClient.get<ExplainResponse>(`/explain/${table}/${record_id}`, undefined, signal),
};
