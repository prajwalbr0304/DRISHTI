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
  IntakeScanApplyRequest,
  IntakeScanApplyResult,
  IntakeScanCapabilityResponse,
  IntakeScanProvenanceResponse,
  IntakeScanQueueResponse,
  IntakeScanResponse,
  IntakeScanTemplateResponse,
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

  /* --- scanned-FIR lane (Catalyst Zia OCR) --------------------------------
     Reading a form never creates a case: `scanOcr` returns a proposal, `applyScan`
     turns the reviewed proposal into a draft, and that draft still goes through
     the same submit + approve gate as a manually typed FIR. */

  /** GET /intake/scan/capability — truthful OCR capability (drives honest UI copy). */
  scanCapability: (signal?: AbortSignal) =>
    apiClient.get<IntakeScanCapabilityResponse>("/intake/scan/capability", undefined, signal),

  /** GET /intake/scan/template — the printable form contract. */
  scanTemplate: (signal?: AbortSignal) =>
    apiClient.get<IntakeScanTemplateResponse>("/intake/scan/template", undefined, signal),

  /** GET /intake/scan/queue — scanned-FIR review queue. */
  scanQueue: (
    params: { status?: string; review_state?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<IntakeScanQueueResponse>("/intake/scan/queue", params, signal),

  /** POST /intake/scan/ocr — read a scanned FIR page. Creates NO draft/case. */
  scanOcr: (
    file: File,
    opts: { languages?: string[]; unitId?: number; idempotencyKey?: string; actor?: string } = {},
    signal?: AbortSignal,
  ) => {
    const form = new FormData();
    form.append("file", file, file.name);
    if (opts.languages?.length) form.append("languages", opts.languages.join(","));
    if (opts.unitId != null) form.append("unit_id", String(opts.unitId));
    if (opts.idempotencyKey) form.append("idempotency_key", opts.idempotencyKey);
    if (opts.actor) form.append("actor", opts.actor);
    return apiClient.upload<IntakeScanResponse>("/intake/scan/ocr", form, { signal });
  },

  /** GET /intake/scan/{key} — a scan and its field proposal. */
  getScan: (scanKey: string, signal?: AbortSignal) =>
    apiClient.get<IntakeScanResponse>(`/intake/scan/${scanKey}`, undefined, signal),

  /** GET /intake/scan/{key}/provenance — what OCR proposed vs what was accepted. */
  scanProvenance: (scanKey: string, signal?: AbortSignal) =>
    apiClient.get<IntakeScanProvenanceResponse>(
      `/intake/scan/${scanKey}/provenance`, undefined, signal),

  /** POST /intake/scan/{key}/apply — reviewed scan -> draft. */
  applyScan: (scanKey: string, body: IntakeScanApplyRequest = {}, signal?: AbortSignal) =>
    apiClient.post<IntakeScanApplyResult>(`/intake/scan/${scanKey}/apply`, body, undefined, signal),

  /** POST /intake/scan/{key}/discard — drop an unapplied scan. */
  discardScan: (scanKey: string, actor?: string, signal?: AbortSignal) =>
    apiClient.post<IntakeScanResponse>(
      `/intake/scan/${scanKey}/discard`, { actor }, undefined, signal),
};

