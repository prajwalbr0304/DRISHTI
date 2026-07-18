import { apiClient } from "@/api/client";
import type {
  EvActivity,
  EvArchiveRequest,
  EvCompleteRequest,
  EvCompleteResponse,
  EvCreateRequest,
  EvCreateResponse,
  EvDownloadUrlResponse,
  EvItem,
  EvLinkRequest,
  EvListResponse,
  EvLookups,
  EvMetadataUpdate,
  EvMigrateResponse,
  EvResetResponse,
  EvStatus,
  EvUploadUrlRequest,
  EvUploadUrlResponse,
} from "@/api/types";

export type EvListParams = {
  case_id?: number;
  evidence_type?: string;
  state?: string;
  q?: string;
  page?: number;
  page_size?: number;
};

/** Digital evidence platform (services/ml/app/evidence). Browser -> FastAPI ->
 *  PostgreSQL/S3 only; file bytes go browser <-> S3 via short-lived pre-signed
 *  URLs the API mints (no AWS credentials ever reach the browser). */
export const evidenceApi = {
  /** GET /evidence/status — S3 + hackathon flags (drives the upload affordance). */
  status: (signal?: AbortSignal) =>
    apiClient.get<EvStatus>("/evidence/status", undefined, signal),

  /** GET /evidence/lookups — types/categories/confidentialities/etc for the form. */
  lookups: (signal?: AbortSignal) =>
    apiClient.get<EvLookups>("/evidence/lookups", undefined, signal),

  /** GET /evidence/items — filterable, paginated evidence list. */
  list: (params: EvListParams = {}, signal?: AbortSignal) =>
    apiClient.get<EvListResponse>("/evidence/items", params, signal),

  /** POST /evidence/items — create a draft item from manual metadata. */
  create: (body: EvCreateRequest, signal?: AbortSignal) =>
    apiClient.post<EvCreateResponse>("/evidence/items", body, undefined, signal),

  /** GET /evidence/items/{id} — full item + objects/versions/links/activity. */
  get: (itemId: number, signal?: AbortSignal) =>
    apiClient.get<EvItem>(`/evidence/items/${itemId}`, undefined, signal),

  /** PUT /evidence/items/{id} — metadata correction (append-only activity). */
  update: (itemId: number, body: EvMetadataUpdate, signal?: AbortSignal) =>
    apiClient.request<EvItem>(`/evidence/items/${itemId}`, { method: "PUT", body, signal }),

  /** GET /evidence/items/{id}/activity — activity timeline. */
  activity: (itemId: number, signal?: AbortSignal) =>
    apiClient.get<EvActivity[]>(`/evidence/items/${itemId}/activity`, undefined, signal),

  /** POST /evidence/items/{id}/upload-url — short-lived pre-signed PUT. */
  uploadUrl: (itemId: number, body: EvUploadUrlRequest, signal?: AbortSignal) =>
    apiClient.post<EvUploadUrlResponse>(`/evidence/items/${itemId}/upload-url`, body, undefined, signal),

  /** POST /evidence/items/{id}/complete — verify object + hash -> object/version. */
  complete: (itemId: number, body: EvCompleteRequest, signal?: AbortSignal) =>
    apiClient.post<EvCompleteResponse>(`/evidence/items/${itemId}/complete`, body, undefined, signal),

  /** POST /evidence/items/{id}/download-url — short-lived pre-signed GET.
   *  disposition 'inline' (preview) or 'attachment' (download, default). */
  downloadUrl: (itemId: number, opts: { versionNo?: number; disposition?: "attachment" | "inline" } = {},
                signal?: AbortSignal) =>
    apiClient.post<EvDownloadUrlResponse>(
      `/evidence/items/${itemId}/download-url`, undefined,
      { version_no: opts.versionNo, disposition: opts.disposition ?? "attachment" }, signal),

  /** POST /evidence/items/{id}/links — link a case/entity. */
  link: (itemId: number, body: EvLinkRequest, signal?: AbortSignal) =>
    apiClient.post<EvItem>(`/evidence/items/${itemId}/links`, body, undefined, signal),

  /** DELETE /evidence/items/{id}/links — unlink a case/entity. */
  unlink: (itemId: number, params: { case_id?: number; canonical_entity_id?: number },
           signal?: AbortSignal) =>
    apiClient.request<EvItem>(`/evidence/items/${itemId}/links`, { method: "DELETE", params, signal }),

  /** POST /evidence/items/{id}/archive — archive (keeps history). */
  archive: (itemId: number, body: EvArchiveRequest = {}, signal?: AbortSignal) =>
    apiClient.post<EvItem>(`/evidence/items/${itemId}/archive`, body, undefined, signal),

  /** POST /evidence/items/{id}/restore — restore an archived item. */
  restore: (itemId: number, signal?: AbortSignal) =>
    apiClient.post<EvItem>(`/evidence/items/${itemId}/restore`, undefined, undefined, signal),

  /** POST /evidence/migrate-legacy — CaseEvidence -> EvidenceItem (idempotent). */
  migrateLegacy: (caseId?: number, signal?: AbortSignal) =>
    apiClient.post<EvMigrateResponse>("/evidence/migrate-legacy", { case_id: caseId }, undefined, signal),

  /** POST /evidence/reset — synthetic-demo reset for a case (admin only). */
  reset: (caseId: number, signal?: AbortSignal) =>
    apiClient.post<EvResetResponse>("/evidence/reset", { case_id: caseId, confirm: true }, undefined, signal),
};
