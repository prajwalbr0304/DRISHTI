import { apiClient } from "@/api/client";

/* ============================================================================
   Phase-13 aggregate station/DISTRICT case-review WORKLOAD band task
   (services/ml/app/workload). The approved replacement for the retired synthetic
   individual offender-risk score: an ordinal, area-level, review-support band —
   never a person-level judgement. Reads are open (aggregate metadata, no PII);
   writes are role-gated + synthetic-DB-guarded server-side. Browser -> FastAPI.
   ========================================================================== */

export interface WorkloadFeature {
  name: string;
  description?: string | null;
  label?: string | null;
  sensitivity: string;
  window?: string | null;
}
export interface WorkloadTaskResponse {
  task: string;
  schema_name: string;
  schema_version: string;
  schema_approved: boolean;
  subject_kind: string;
  bands: string[];
  label_definition: string;
  label_horizon_months: number;
  aggregate_only: boolean;
  not_person_level: boolean;
  features: WorkloadFeature[];
  limitations: string;
  model_card: Record<string, unknown>;
  environment_label: string;
}

export interface WorkloadModelInfo {
  model_version_id: number;
  model_name: string;
  version: string;
  model_type: string;
  approval_status?: string | null;
  status?: string | null;
  environment?: string | null;
  feature_schema_version_id?: number | null;
  training_dataset_snapshot_id?: number | null;
  metrics: Record<string, unknown>;
}
export interface WorkloadModelListResponse {
  models: WorkloadModelInfo[];
  served_model_version_id?: number | null;
}

export interface WorkloadPredictionRow {
  prediction_result_id: number;
  prediction_request_id?: number | null;
  unit_id: string;
  unit_name?: string | null;
  district_id?: number | null;
  observation_cutoff?: string | null;
  workload_band?: string | null;
  band_ordinal?: number | null;
  band_probabilities: Record<string, number>;
  confidence?: number | null;
  abstained?: boolean | null;
  recent_case_volume?: number | null;
  is_stale: boolean;
  model_version?: string | null;
  created_at?: string | null;
  actual_backend?: string | null;
  actual_device?: string | null;
  gpu_name?: string | null;
  served_via?: string | null;
  model_artifact_digest?: string | null;
}
export interface WorkloadPredictionListResponse {
  predictions: WorkloadPredictionRow[];
  total: number;
  page: number;
  page_size: number;
  cutoff_period?: string | null;
  aggregate_only: boolean;
  limitations: string;
}

export interface WorkloadMetricBlock {
  n: number;
  accuracy: number;
  macro_f1: number;
  qwk: number;
  brier?: number;
  ece: number;
}
export interface WorkloadBaselineReport extends WorkloadMetricBlock {
  name: string;
  family: string;
}
export interface WorkloadEvaluationResponse {
  task: string;
  schema: string;
  bands: string[];
  band_thresholds: number[];
  model: {
    name: string;
    family: string;
    foundation_kind: string;
    temperature: number;
    calibrated: WorkloadMetricBlock;
    uncalibrated: WorkloadMetricBlock;
    per_class: Array<{ band: number; precision: number; recall: number; f1: number; support: number }>;
    confusion: number[][];
  };
  baselines: Record<string, WorkloadBaselineReport>;
  skill_vs_baselines: Record<string, number | null>;
  beats_all_baselines: boolean;
  abstention: {
    confidence_threshold: number;
    min_history_months: number;
    abstained: number;
    n_test: number;
    abstention_rate: number;
    metrics_on_retained?: WorkloadMetricBlock | null;
    threshold_review: Array<{ confidence_threshold: number; coverage: number; accuracy_on_retained: number | null }>;
  };
  metrics_by_time: Record<string, WorkloadMetricBlock>;
  metrics_by_geography: Record<string, WorkloadMetricBlock>;
  metrics_by_data_completeness: Record<string, WorkloadMetricBlock>;
  geo_holdout: Record<string, unknown>;
  leakage: {
    protected_or_proxy_features: string[];
    has_protected_or_proxy: boolean;
    label_independent_of_features: boolean;
    label_window_after_cutoff: boolean;
    max_feature_label_correlation: number;
    max_correlation_feature?: string | null;
    suspected_leak: boolean;
    leakage_safe: boolean;
  };
  splits: Record<string, number>;
  dataset: Record<string, unknown>;
}

export interface WorkloadBenchmarkRow {
  model_name: string;
  family?: string | null;
  scale_label?: string | null;
  row_scale: number;
  device?: string | null;
  fit_seconds?: number | null;
  predict_seconds?: number | null;
  total_seconds?: number | null;
  latency_ms_per_row?: number | null;
  throughput_rows_per_sec?: number | null;
  peak_rss_mb?: number | null;
  gpu_mem_mb?: number | null;
  accuracy?: number | null;
  macro_f1?: number | null;
  qwk?: number | null;
  ece?: number | null;
  cost_estimate: Record<string, unknown>;
  available: boolean;
  note?: string | null;
  created_at?: string | null;
}
export interface WorkloadBenchmarkListResponse {
  benchmarks: WorkloadBenchmarkRow[];
  assumptions: Record<string, unknown>;
}

export interface WorkloadRunBody {
  foundation_kind?: string;
  limit?: number | null;
  lifecycle?: string;
  actor?: string;
}
export interface WorkloadRunResponse {
  model_version_id: number;
  feature_schema_version_id: number;
  training_dataset_snapshot_id: number;
  backend: string;
  cutoff: string;
  stations: number;
  snapshots_new: number;
  snapshots_reused: number;
  requests_new: number;
  results_new: number;
  superseded_prior: number;
  metrics: Record<string, unknown>;
}
export interface WorkloadLifecycleResponse {
  model_version_id: number;
  status: string;
  approval_status: string;
}

export const workloadApi = {
  task: (signal?: AbortSignal) =>
    apiClient.get<WorkloadTaskResponse>("/workload/task", undefined, signal),
  models: (signal?: AbortSignal) =>
    apiClient.get<WorkloadModelListResponse>("/workload/models", undefined, signal),
  predictions: (
    opts: { page?: number; page_size?: number; include_stale?: boolean } = {},
    signal?: AbortSignal,
  ) => apiClient.get<WorkloadPredictionListResponse>("/workload/predictions", { page: 1, page_size: 50, ...opts }, signal),
  evaluation: (
    opts: { foundation_kind?: string; refresh?: boolean } = {},
    signal?: AbortSignal,
  ) => apiClient.get<WorkloadEvaluationResponse>("/workload/evaluation", opts, signal),
  benchmarks: (signal?: AbortSignal) =>
    apiClient.get<WorkloadBenchmarkListResponse>("/workload/benchmarks", undefined, signal),

  // --- writes (role-gated + synthetic-DB guard server-side) ---
  run: (body: WorkloadRunBody = {}, signal?: AbortSignal) =>
    apiClient.post<WorkloadRunResponse>("/workload/run", body, undefined, signal),
  runBenchmark: (includeHeavy = false, signal?: AbortSignal) =>
    apiClient.post<WorkloadBenchmarkListResponse>("/workload/benchmark", undefined, { include_heavy: includeHeavy }, signal),
  setLifecycle: (modelVersionId: number, stage: string, actor?: string, signal?: AbortSignal) =>
    apiClient.post<WorkloadLifecycleResponse>(
      `/workload/models/${modelVersionId}/lifecycle`, { stage, actor }, undefined, signal),
};
