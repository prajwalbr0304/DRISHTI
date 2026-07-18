import { apiClient } from "@/api/client";
import type {
  IntakeApprovalResult,
  IntakeCasePartyListResponse,
  IntakeCreateDraftRequest,
  IntakeDataQualityListResponse,
  IntakeDraftActivity,
  IntakeDraftListResponse,
  IntakeDraftResponse,
  IntakeDuplicateCheckResponse,
  IntakeJurisdictionInfo,
  IntakeLookupsResponse,
  IntakePartyInput,
  IntakeStatusResponse,
  IntakeUpdateDraftRequest,
  IntakeValidationResponse,
  IntakeCaseEventResponse,
  IntakeWorkflowMetaResponse,
} from "@/api/types";

export type IntakeReviewAction = "approve" | "reject" | "return";

/** Structured FIR/case intake (services/ml/app/intake). Browser -> FastAPI only. */
export const intakeApi = {
  /** GET /intake/status — hackathon flags (drives the submit gate + demo badge). */
  status: (signal?: AbortSignal) =>
    apiClient.get<IntakeStatusResponse>("/intake/status", undefined, signal),

  /** GET /intake/lookups — reference/options for the wizard (optionally unit-scoped). */
  lookups: (unitId?: number, signal?: AbortSignal) =>
    apiClient.get<IntakeLookupsResponse>("/intake/lookups", { unit_id: unitId }, signal),

  /** GET /intake/workflow — kinds + statuses + category transition metadata. */
  workflow: (signal?: AbortSignal) =>
    apiClient.get<IntakeWorkflowMetaResponse>("/intake/workflow", undefined, signal),

  /** GET /intake/quality/issues — staging data-quality review queue (read-only). */
  qualityIssues: (
    params: { status?: string; severity?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<IntakeDataQualityListResponse>("/intake/quality/issues", params, signal),

  /** GET /intake/cases/{caseId}/parties — canonical case parties (CasePartyRole). */
  caseParties: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<IntakeCasePartyListResponse>(`/intake/cases/${caseId}/parties`, undefined, signal),

  /** POST /intake/geo/resolve — jurisdiction/containment for an incident point. */
  geoResolve: (
    body: { latitude?: number | null; longitude?: number | null; assigned_district_id?: number | null },
    signal?: AbortSignal,
  ) => apiClient.post<IntakeJurisdictionInfo>("/intake/geo/resolve", body, undefined, signal),

  /** GET /intake/drafts — intake inbox (filter/paginate). */
  listDrafts: (
    params: { status?: string; case_kind?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<IntakeDraftListResponse>("/intake/drafts", params, signal),

  /** POST /intake/drafts — create a draft (idempotent via idempotency_key). */
  createDraft: (body: IntakeCreateDraftRequest, signal?: AbortSignal) =>
    apiClient.post<IntakeDraftResponse>("/intake/drafts", body, undefined, signal),

  /** GET /intake/drafts/{key} — full draft. */
  getDraft: (draftKey: string, signal?: AbortSignal) =>
    apiClient.get<IntakeDraftResponse>(`/intake/drafts/${draftKey}`, undefined, signal),

  /** PUT /intake/drafts/{key} — update / autosave. */
  updateDraft: (draftKey: string, body: IntakeUpdateDraftRequest, signal?: AbortSignal) =>
    apiClient.request<IntakeDraftResponse>(`/intake/drafts/${draftKey}`, { method: "PUT", body, signal }),

  /** POST /intake/drafts/{key}/validate — errors (blocking) vs warnings (review). */
  validateDraft: (draftKey: string, signal?: AbortSignal) =>
    apiClient.post<IntakeValidationResponse>(`/intake/drafts/${draftKey}/validate`, undefined, undefined, signal),

  /** POST /intake/drafts/{key}/duplicate-check — duplicate/source-key candidates. */
  duplicateCheck: (draftKey: string, externalSourceId?: string, signal?: AbortSignal) =>
    apiClient.post<IntakeDuplicateCheckResponse>(
      `/intake/drafts/${draftKey}/duplicate-check`, { external_source_id: externalSourceId }, undefined, signal),

  /** GET /intake/drafts/{key}/activity — autosave/submit/review trail. */
  activity: (draftKey: string, signal?: AbortSignal) =>
    apiClient.get<IntakeDraftActivity[]>(`/intake/drafts/${draftKey}/activity`, undefined, signal),

  /** POST /intake/drafts/{key}/parties — add a case-party role. */
  addParty: (draftKey: string, body: IntakePartyInput, signal?: AbortSignal) =>
    apiClient.post<IntakeDraftResponse>(`/intake/drafts/${draftKey}/parties`, body, undefined, signal),

  /** PUT /intake/drafts/{key}/parties/{id} — update a party. */
  updateParty: (draftKey: string, partyId: number, body: IntakePartyInput, signal?: AbortSignal) =>
    apiClient.request<IntakeDraftResponse>(
      `/intake/drafts/${draftKey}/parties/${partyId}`, { method: "PUT", body, signal }),

  /** DELETE /intake/drafts/{key}/parties/{id} — remove a party. */
  removeParty: (draftKey: string, partyId: number, signal?: AbortSignal) =>
    apiClient.request<IntakeDraftResponse>(
      `/intake/drafts/${draftKey}/parties/${partyId}`, { method: "DELETE", signal }),

  /** POST /intake/drafts/{key}/submit — submit for review (submit-gated). */
  submit: (draftKey: string, actor?: string, signal?: AbortSignal) =>
    apiClient.post<IntakeDraftResponse>(`/intake/drafts/${draftKey}/submit`, { actor }, undefined, signal),

  /** POST /intake/drafts/{key}/review — approve/reject/return (submit-gated). */
  review: (draftKey: string, action: IntakeReviewAction, body: { actor?: string; note?: string } = {}, signal?: AbortSignal) =>
    apiClient.post<IntakeApprovalResult | { draft: IntakeDraftResponse }>(
      `/intake/drafts/${draftKey}/review`, body, { action }, signal),

  /** POST /intake/cases/{caseId}/events — workflow-gated lifecycle event (submit-gated). */
  createCaseEvent: (
    caseId: number,
    body: { event_type: string; occurred_at?: string; actor_role?: string; payload?: Record<string, unknown> },
    signal?: AbortSignal,
  ) => apiClient.post<IntakeCaseEventResponse>(`/intake/cases/${caseId}/events`, body, undefined, signal),
};

