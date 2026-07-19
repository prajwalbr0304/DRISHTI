import { apiClient } from "@/api/client";
import type { ReportTemplate } from "@/api/endpoints/admin";

/* Phase-15 reports (services/ml/app/reports). Generated from structured DB
   fields only (no OCR/file parsing); every snapshot carries a reproducible
   source snapshot, a SHA-256, source/version citations and a synthetic
   watermark, and is stored in private Stratus. Browser -> FastAPI only. */

export interface ReportSnapshot {
  report_snapshot_id: number;
  report_template_id?: number | null;
  template_code?: string | null;
  title: string;
  requested_by_actor?: string | null;
  requested_by_role?: string | null;
  scope_kind: string;
  scope_ref_id?: string | null;
  filters: Record<string, unknown>;
  source_snapshot: Record<string, unknown>;
  source_citations: Record<string, unknown>[];
  content_hash: string;
  watermark: string;
  stratus_bucket?: string | null;
  stratus_object_key?: string | null;
  stratus_version_id?: string | null;
  object_sha256?: string | null;
  object_size_bytes?: number | null;
  content_type?: string | null;
  render_backend?: string | null;
  status: string;
  version: number;
  expires_at?: string | null;
  created_at?: string | null;
}
export interface ReportListItem {
  report_snapshot_id: number;
  template_code?: string | null;
  title: string;
  scope_kind: string;
  scope_ref_id?: string | null;
  requested_by_actor?: string | null;
  content_hash: string;
  object_sha256?: string | null;
  render_backend?: string | null;
  status: string;
  created_at?: string | null;
}
export interface ReportDownload {
  report_snapshot_id: number;
  url: string;
  expires_in_seconds: number;
  object_sha256?: string | null;
  watermark: string;
}
export interface ReportVerify {
  report_snapshot_id: number;
  reproducible: boolean;
  stored_hash: string;
  recomputed_hash: string;
}
export interface ReportGenerateBody {
  template_code: string;
  scope_kind?: string;
  scope_ref_id?: string;
  title?: string;
  filters?: Record<string, unknown>;
}

export const reportsApi = {
  templates: (s?: AbortSignal) =>
    apiClient.get<{ items: ReportTemplate[] }>("/reports/templates", undefined, s),
  list: (opts: { scope_kind?: string; scope_ref_id?: string; limit?: number } = {}, s?: AbortSignal) =>
    apiClient.get<{ total: number; items: ReportListItem[] }>("/reports", { limit: 50, ...opts }, s),
  generate: (body: ReportGenerateBody, s?: AbortSignal) =>
    apiClient.post<ReportSnapshot>("/reports", body, undefined, s),
  get: (id: number, s?: AbortSignal) =>
    apiClient.get<ReportSnapshot>(`/reports/${id}`, undefined, s),
  verify: (id: number, s?: AbortSignal) =>
    apiClient.get<ReportVerify>(`/reports/${id}/verify`, undefined, s),
  download: (id: number, s?: AbortSignal) =>
    apiClient.post<ReportDownload>(`/reports/${id}/download`, undefined, undefined, s),
};
