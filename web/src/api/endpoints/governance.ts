import { apiClient } from "@/api/client";
import type {
  GovBuildSnapshotResult,
  GovFeatureDefinitionListResponse,
  GovFeatureSchemaListResponse,
  GovFeatureSnapshotListResponse,
  GovInvalidateResult,
  GovModelVersionListResponse,
  GovOutcomeLabelListResponse,
  GovPredictionDetail,
  GovPredictionRequestListResponse,
} from "@/api/types";

export interface GovBuildSnapshotBody {
  feature_schema_version_id: number;
  subject_kind?: string;
  subject_ref_id: string;
  observation_cutoff?: string | null;
  actor?: string;
}
export interface GovCreatePredictionBody {
  model_version_id: number;
  feature_snapshot_id: number;
  request_kind?: "batch" | "adhoc" | "shadow";
  idempotency_key?: string;
  actor?: string;
}
export interface GovReviewBody {
  decision: "accept" | "override" | "reject";
  override_reason?: string | null;
  actor?: string;
}

/**
 * Phase-10 governed feature & prediction contracts (services/ml/app/governance).
 * The safe bridge between verified inputs and any model. Reads are open
 * (aggregate governance metadata, no PII); writes are role-gated server-side.
 * Predictions are aggregate decision-support only and every result ties to an
 * immutable feature snapshot. Browser -> FastAPI only.
 */
export const governanceApi = {
  // --- registry (reads) ---
  features: (signal?: AbortSignal) =>
    apiClient.get<GovFeatureDefinitionListResponse>("/governance/features", undefined, signal),
  schemas: (signal?: AbortSignal) =>
    apiClient.get<GovFeatureSchemaListResponse>("/governance/schemas", undefined, signal),
  models: (governedOnly = true, signal?: AbortSignal) =>
    apiClient.get<GovModelVersionListResponse>("/governance/models", { governed_only: governedOnly }, signal),
  snapshots: (
    opts: { subject_kind?: string; subject_ref_id?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<GovFeatureSnapshotListResponse>("/governance/snapshots", { page: 1, page_size: 50, ...opts }, signal),
  labels: (
    opts: { split?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<GovOutcomeLabelListResponse>("/governance/labels", { page: 1, page_size: 50, ...opts }, signal),
  predictions: (
    opts: { status?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<GovPredictionRequestListResponse>("/governance/predictions", { page: 1, page_size: 50, ...opts }, signal),
  prediction: (requestId: number, signal?: AbortSignal) =>
    apiClient.get<GovPredictionDetail>(`/governance/predictions/${requestId}`, undefined, signal),

  // --- writes (role-gated + synthetic-DB guard server-side) ---
  buildSnapshot: (body: GovBuildSnapshotBody, signal?: AbortSignal) =>
    apiClient.post<GovBuildSnapshotResult>("/governance/snapshots/build", body, undefined, signal),
  invalidateSnapshot: (
    body: { subject_kind: string; subject_ref_id: string; reason: string; actor?: string },
    signal?: AbortSignal,
  ) => apiClient.post<GovInvalidateResult>("/governance/snapshots/invalidate", body, undefined, signal),
  createPrediction: (body: GovCreatePredictionBody, signal?: AbortSignal) =>
    apiClient.post<GovPredictionDetail>("/governance/predictions", body, undefined, signal),
  runPrediction: (requestId: number, actor?: string, signal?: AbortSignal) =>
    apiClient.post<GovPredictionDetail>(`/governance/predictions/${requestId}/run`, { actor }, undefined, signal),
  reviewPrediction: (requestId: number, body: GovReviewBody, signal?: AbortSignal) =>
    apiClient.post<GovPredictionDetail>(`/governance/predictions/${requestId}/review`, body, undefined, signal),
  rollbackModel: (modelVersionId: number, toModelVersionId?: number, signal?: AbortSignal) =>
    apiClient.post<GovModelVersionListResponse>(
      `/governance/models/${modelVersionId}/rollback`,
      undefined,
      toModelVersionId != null ? { to_model_version_id: toModelVersionId } : undefined,
      signal,
    ),
};
