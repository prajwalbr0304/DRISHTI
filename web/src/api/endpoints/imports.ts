import { apiClient } from "@/api/client";
import type {
  ImpAccountListResponse,
  ImpBatch,
  ImpBatchListResponse,
  ImpCdrTimelineResponse,
  ImpCommitResult,
  ImpDeviceListResponse,
  ImpEntityLinkQueueResponse,
  ImpMoneyAlertListResponse,
  ImpMoneyScanResponse,
  ImpRollbackResult,
  ImpStagingRowListResponse,
  ImpTemplateListResponse,
  ImpTransactionListResponse,
} from "@/api/types";

export interface ImpCreateBatchBody {
  import_template_version_id: number;
  content: string;
  source_format: "csv" | "json";
  source_file_name?: string;
  case_master_id?: number;
  evidence_item_id?: number;
  mapping_override?: Record<string, string>;
  idempotency_key?: string;
  created_by_actor?: string;
}

/**
 * Phase-8 digital + financial imports (services/ml/app/imports). Structured
 * CSV/JSON only (no OCR). Browser -> FastAPI only. Files are uploaded as
 * evidence; only committed, provenanced rows affect anything; graph links are
 * created as candidates and must be reviewed. Financial views are gated by the
 * money_trail permission server-side.
 */
export const importsApi = {
  templates: (signal?: AbortSignal) =>
    apiClient.get<ImpTemplateListResponse>("/imports/templates", undefined, signal),

  // --- batches / staging ---
  listBatches: (
    opts: { status?: string; domain?: string; case_id?: number; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<ImpBatchListResponse>("/imports/batches", { page: 1, page_size: 25, ...opts }, signal),
  createBatch: (body: ImpCreateBatchBody, signal?: AbortSignal) =>
    apiClient.post<ImpBatch>("/imports/batches", body, undefined, signal),
  getBatch: (id: number, signal?: AbortSignal) =>
    apiClient.get<ImpBatch>(`/imports/batches/${id}`, undefined, signal),
  rows: (id: number, opts: { status?: string; page?: number; page_size?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<ImpStagingRowListResponse>(`/imports/batches/${id}/rows`, { page: 1, page_size: 200, ...opts }, signal),
  commit: (id: number, actor?: string, signal?: AbortSignal) =>
    apiClient.post<ImpCommitResult>(`/imports/batches/${id}/commit`, { actor }, undefined, signal),
  rollback: (id: number, body: { actor?: string; reason?: string } = {}, signal?: AbortSignal) =>
    apiClient.post<ImpRollbackResult>(`/imports/batches/${id}/rollback`, body, undefined, signal),
  supersede: (
    id: number,
    body: { content: string; source_format: "csv" | "json"; source_file_name?: string;
            mapping_override?: Record<string, string>; actor?: string; reason?: string },
    signal?: AbortSignal,
  ) => apiClient.post<ImpBatch>(`/imports/batches/${id}/supersede`, body, undefined, signal),

  // --- reviewed entity-link queue ---
  entityLinks: (
    opts: { review_status?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<ImpEntityLinkQueueResponse>("/imports/entity-links", { page: 1, page_size: 50, ...opts }, signal),
  reviewEntityLink: (id: number, decision: "accept" | "reject", actor?: string, note?: string, signal?: AbortSignal) =>
    apiClient.post(`/imports/entity-links/${id}/review`, { decision, actor, note }, undefined, signal),

  // --- CDR / device views ---
  cdrTimeline: (scope: { case_id: number } | { entity_id: number }, limit = 500, signal?: AbortSignal) =>
    apiClient.get<ImpCdrTimelineResponse>("/imports/cdr/timeline", { ...scope, limit }, signal),
  devices: (scope: { case_id: number } | { entity_id: number }, signal?: AbortSignal) =>
    apiClient.get<ImpDeviceListResponse>("/imports/devices", scope, signal),

  // --- financial views + money alerts (money_trail permission) ---
  accounts: (
    opts: { flagged?: boolean; review_status?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<ImpAccountListResponse>("/imports/accounts", { page: 1, page_size: 25, ...opts }, signal),
  transactions: (
    opts: { account_id?: number; flagged?: boolean; case_id?: number; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<ImpTransactionListResponse>("/imports/transactions", { page: 1, page_size: 25, ...opts }, signal),
  moneyAlerts: (
    opts: { status?: string; alert_type?: string; case_id?: number; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<ImpMoneyAlertListResponse>("/imports/money/alerts", { page: 1, page_size: 25, ...opts }, signal),
  moneyScan: (
    params: { structuring_min_count?: number; structuring_window_days?: number;
              cycle_min_amount?: number; cycle_max_len?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.post<ImpMoneyScanResponse>("/imports/money/scan", undefined, params, signal),
  moneyDisposition: (
    id: number,
    body: { disposition: string; actor?: string; reason?: string },
    signal?: AbortSignal,
  ) => apiClient.post(`/imports/money/alerts/${id}/disposition`, body, undefined, signal),
};
