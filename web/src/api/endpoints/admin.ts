import { apiClient } from "@/api/client";

/* Phase-15 admin/governance console (services/ml/app/admin). Reads require an
   admin_read role (supervisor + super_admin); config writes require super_admin
   AND the hackathon write guard, enforced server-side. Browser -> FastAPI only. */

export interface AdminComponentFlags {
  signals_enabled: boolean;
  notify_enabled: boolean;
  rag_enabled: boolean;
  use_catalyst_datastore: boolean;
  use_catalyst_stratus: boolean;
  use_catalyst_smartbrowz: boolean;
}
export interface AdminStatus {
  hackathon_mode: boolean;
  demo_data_only: boolean;
  synthetic_db: boolean;
  environment_label: string;
  rls_disabled: boolean;
  rls_tables_checked: number;
  rls_tables_enabled: number;
  database_ok: boolean;
  components: AdminComponentFlags;
  counts: Record<string, number>;
}
export interface RlsTable {
  schema_name: string;
  table_name: string;
  rls_enabled: boolean;
  rls_forced: boolean;
}
export interface RlsStatus {
  rls_disabled: boolean;
  tables_checked: number;
  tables_enabled: number;
  offenders: string[];
  tables: RlsTable[];
}
export interface AuthorizationMatrix {
  roles: string[];
  permissions: string[];
  matrix: Record<string, Record<string, boolean>>;
  resolved_role: string;
}
export interface AdminUnit {
  unit_id: number;
  unit_name: string;
  district_id?: number | null;
  district_name?: string | null;
  active: boolean;
  case_count: number;
}
export interface ReconciliationRow {
  source_system_id: number;
  code: string;
  name: string;
  kind: string;
  total_source_records: number;
  committed_records: number;
  rejected_records: number;
  duplicate_records: number;
  pending_records: number;
  total_jobs: number;
  partial_jobs: number;
  failed_jobs: number;
  last_received_at?: string | null;
}
export interface AuditEvent {
  audit_event_id: number;
  occurred_at?: string | null;
  actor?: string | null;
  actor_role?: string | null;
  action?: string | null;
  resource?: string | null;
  resource_id?: string | null;
  detail: Record<string, unknown>;
}
export interface RetentionPolicy {
  retention_policy_id: number;
  code: string;
  name: string;
  applies_to: string;
  retention_days: number;
  archive_after_days?: number | null;
  expiry_action: string;
  description?: string | null;
  is_active: boolean;
}
export interface LegalHold {
  legal_hold_id: number;
  subject_kind: string;
  subject_ref_id: string;
  reason: string;
  status: string;
  placed_by_actor?: string | null;
  placed_at?: string | null;
  released_by_actor?: string | null;
  released_at?: string | null;
}
export interface RetentionOverview {
  policies: RetentionPolicy[];
  legal_holds: LegalHold[];
  evidence_summary: Record<string, number>;
  non_destructive: boolean;
}
export interface ModelReviewRow {
  model_version_id: number;
  model_name: string;
  version: string;
  approval_status?: string | null;
  environment?: string | null;
  approved_at?: string | null;
  model_review_id?: number | null;
  review_kind?: string | null;
  review_status?: string | null;
  due_at?: string | null;
  drift_signal: Record<string, unknown>;
  effective_review_state: string;
}
export interface AdminQueues {
  data_quality_open: number;
  ingestion_partial_failed: number;
  evidence_quarantine: number;
  /** True only for the intake-FORM reading queue. Evidence media is never parsed. */
  extraction_queue_present: boolean;
  intake_scan_pending?: number;
  evidence_extraction_enabled?: boolean;
  data_quality_items: Record<string, unknown>[];
  quarantine_items: Record<string, unknown>[];
}
export interface FeatureFlag {
  key: string;
  enabled: boolean;
  category: string;
  description?: string | null;
  runtime_effective?: boolean | null;
}
export interface AdminUsage {
  plan_baseline: Record<string, unknown>;
  budget_alerts: Record<string, unknown>[];
  feature_flags: FeatureFlag[];
  note: string;
}
export interface ReportTemplate {
  report_template_id: number;
  code: string;
  name: string;
  description?: string | null;
  report_kind: string;
  scope_kind: string;
  allowed_roles: string[];
  config_schema: Record<string, unknown>;
  is_active: boolean;
}

export const adminApi = {
  status: (s?: AbortSignal) => apiClient.get<AdminStatus>("/admin/status", undefined, s),
  rlsStatus: (s?: AbortSignal) => apiClient.get<RlsStatus>("/admin/rls-status", undefined, s),
  identity: (s?: AbortSignal) => apiClient.get<AuthorizationMatrix>("/admin/identity", undefined, s),
  units: (s?: AbortSignal) =>
    apiClient.get<{ total: number; items: AdminUnit[] }>("/admin/units", undefined, s),
  sourceSystems: (s?: AbortSignal) =>
    apiClient.get<{ total: number; boundaries: Record<string, number>; items: unknown[] }>(
      "/admin/source-systems", undefined, s),
  reconciliation: (s?: AbortSignal) =>
    apiClient.get<{ total: number; items: ReconciliationRow[] }>("/admin/reconciliation", undefined, s),
  repair: (body: { ingestion_job_id?: number; source_record_ids?: number[]; reason: string }, s?: AbortSignal) =>
    apiClient.post("/admin/reconciliation/repair", body, undefined, s),
  audit: (
    params: { action?: string; resource?: string; actor?: string; text?: string; page?: number; page_size?: number } = {},
    s?: AbortSignal,
  ) => apiClient.get<{ total: number; page: number; page_size: number; items: AuditEvent[] }>(
    "/admin/audit", { page: 1, page_size: 50, ...params }, s),
  retention: (s?: AbortSignal) => apiClient.get<RetentionOverview>("/admin/retention", undefined, s),
  placeLegalHold: (body: { subject_kind: string; subject_ref_id: string; reason: string }, s?: AbortSignal) =>
    apiClient.post<LegalHold>("/admin/legal-holds", body, undefined, s),
  releaseLegalHold: (id: number, s?: AbortSignal) =>
    apiClient.post<LegalHold>(`/admin/legal-holds/${id}/release`, undefined, undefined, s),
  models: (s?: AbortSignal) =>
    apiClient.get<{ total: number; items: ModelReviewRow[] }>("/admin/models", undefined, s),
  reviewModel: (id: number, body: { review_kind?: string; status?: string; findings?: Record<string, unknown>; drift_signal?: Record<string, unknown> }, s?: AbortSignal) =>
    apiClient.post(`/admin/models/${id}/review`, body, undefined, s),
  queues: (s?: AbortSignal) => apiClient.get<AdminQueues>("/admin/queues", undefined, s),
  usage: (s?: AbortSignal) => apiClient.get<AdminUsage>("/admin/usage", undefined, s),
  setFeatureFlag: (key: string, enabled: boolean, s?: AbortSignal) =>
    apiClient.post<FeatureFlag>(`/admin/feature-flags/${key}`, { enabled }, undefined, s),
  reportTemplates: (s?: AbortSignal) =>
    apiClient.get<{ items: ReportTemplate[] }>("/admin/report-templates", undefined, s),
};
